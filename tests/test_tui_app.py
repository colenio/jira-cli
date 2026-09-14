"""Tests for the interactive Jira TUI (JiraApp), driven headlessly via Textual's pilot."""

import pytest
from textual.widgets import Input

from jira_cli.models import IssueRow
from jira_cli.providers import ProviderContext, ProviderDescriptor
from jira_cli.quick_filters import normalize_for_match
from jira_cli.tui.app import JiraApp
from jira_cli.tui.features.board.service import group_by_status
from jira_cli.tui.features.board.widgets import BoardWidget


class FakeJiraClient:
    """Minimal client stub the TUI needs, without hitting the network or printing."""

    base_url = "https://example.atlassian.net"

    def __init__(self, assignable_users: list[str] | None = None):
        self.assignable_users = [
            {"displayName": name, "emailAddress": f"{name.split()[0].lower()}@example.com"}
            for name in (assignable_users or [])
        ]
        self.comment_calls: list[str] = []
        self.update_calls: list[tuple[str, dict]] = []

    def get_issue_comments(self, key: str, expand_changelog: bool = False) -> list[dict]:
        self.comment_calls.append(key)
        return []

    def update_issue(self, key: str, fields: dict) -> None:
        self.update_calls.append((key, fields))

    def describe(self) -> ProviderDescriptor:
        return ProviderDescriptor(name="fake", query_language="JQL")

    def get_current_user(self) -> dict:
        return {"displayName": "Marcel Körtgen", "emailAddress": "marcel@example.com", "accountId": "abc-123"}

    def find_assignable_users(self, project_key: str, query: str, max_results: int = 20) -> list[dict]:
        normalized_query = normalize_for_match(query)
        return [u for u in self.assignable_users if normalized_query in normalize_for_match(u["displayName"])]

    def list_assignable_users(self, project_key: str, max_results: int = 50) -> list[dict]:
        return list(self.assignable_users)

    def search_users(self, query: str, max_results: int = 20) -> list[dict]:
        return []

    def list_versions(self, project_key: str) -> list[dict]:
        return [{"name": "2026.09", "released": False, "archived": False, "releaseDate": "2026-09-30"}]

    def list_labels(self, project_key: str) -> list[dict]:
        return [{"name": "backend", "issueCount": 2}, {"name": "frontend", "issueCount": 1}]


def _issue_labels(issue: IssueRow) -> list[str]:
    return [label.strip() for label in (issue.labels or "").split(",") if label.strip()]


def make_fake_search_custom_jql(server_issues: list[IssueRow], current_user_name: str = ""):
    """Build a tiny JQL evaluator for our own generated 'project = X AND field = "value"' clauses.

    Emulates server-side filtering against the full `server_issues` dataset, independent of
    whatever subset happens to be currently loaded in the app (that's the whole point: quick
    filters must be server-side, not limited to an already-loaded page).
    """

    def search_custom_jql(jql: str, fields=None, max_results: int = 50) -> list[IssueRow]:
        query_part, _, order_part = jql.partition(" ORDER BY ")
        conditions = [c.strip() for c in query_part.split(" AND ")]

        def matches(issue: IssueRow) -> bool:
            for cond in conditions:
                if cond.startswith("project"):
                    continue
                if cond == "assignee = currentUser()":
                    if issue.assignee != current_user_name:
                        return False
                    continue
                field, _, raw_value = cond.partition("=")
                field = field.strip()
                value = raw_value.strip().strip('"')
                if field == "issuetype" and issue.issue_type != value:
                    return False
                if field == "status" and issue.status != value:
                    return False
                if field == "assignee" and issue.assignee != value:
                    return False
                if field == "labels" and value not in _issue_labels(issue):
                    return False
                if field == "priority" and issue.priority != value:
                    return False
                if field == "key" and issue.key != value:
                    return False
            return True

        rows = [issue for issue in server_issues if matches(issue)]
        if order_part:
            parts = order_part.split()
            field = parts[0]
            reverse = len(parts) > 1 and parts[1].upper() == "DESC"
            accessors = {
                "key": lambda issue: issue.key,
                "priority": lambda issue: issue.priority or "",
                "updated": lambda issue: issue.updated or "",
            }
            if field in accessors:
                rows = sorted(rows, key=accessors[field], reverse=reverse)
        return rows

    return search_custom_jql


@pytest.fixture
def sample_issues() -> list[IssueRow]:
    return [
        IssueRow(
            key="A-1",
            summary="First",
            issue_type="Story",
            status="To Do",
            priority="Medium",
            assignee="Alice",
            labels="frontend",
        ),
        IssueRow(
            key="A-2",
            summary="Second",
            issue_type="Bug",
            status="In Progress",
            priority="High",
            assignee="Bob",
            labels="backend, urgent",
        ),
        IssueRow(
            key="A-3", summary="Third", issue_type="Story", status="Done", priority="Low", assignee="Alice", labels="backend"
        ),
        IssueRow(key="A-4", summary="Fourth", issue_type="Epic", status="To Do", priority="Low", assignee="", labels=""),
        IssueRow(
            key="A-5",
            summary="Fifth",
            issue_type="Task",
            status="To Do",
            priority="Highest",
            assignee="Marcel Körtgen",
            labels="",
        ),
    ]


@pytest.fixture
def app(sample_issues) -> JiraApp:
    all_assignees = sorted({i.assignee for i in sample_issues if i.assignee})
    app = JiraApp(
        FakeJiraClient(assignable_users=all_assignees), "A", sample_issues, current_user_display_name="Marcel Körtgen"
    )
    # Quick filters now always round-trip through JQL (server-side); stub that round-trip
    # against the same dataset instead of hitting a real Jira instance.
    app.query.search_custom_jql = make_fake_search_custom_jql(sample_issues, current_user_name="Marcel Körtgen")
    return app


async def test_initial_selection(app):
    async with app.run_test():
        selected = app._selected_issue()
        assert selected is not None
        assert selected.key == "A-1"


async def test_issue_detail_rendering_does_not_fetch_comments(sample_issues):
    client = FakeJiraClient()
    app = JiraApp(client, "A", sample_issues, current_user_display_name="Marcel Körtgen")
    app._prefetch_comments_for_issue = lambda issue: None
    async with app.run_test():
        before = list(client.comment_calls)
        app.update_issue_detail(sample_issues[1])
        assert client.comment_calls == before


async def test_topbar_user_does_not_overlap_clock(app):
    async with app.run_test() as pilot:
        await pilot.pause()
        user = app.query_one("#topbar_user")
        clock = app.query_one("#topbar_clock")
        assert user.region.x + user.region.width <= clock.region.x


def test_provider_query_placeholder_uses_github_example(sample_issues):
    client = FakeJiraClient()
    app = JiraApp(
        client,
        "colenio/jira-cli",
        sample_issues,
        context=ProviderContext(
            name="github:colenio/jira-cli",
            provider="github",
            target="colenio/jira-cli",
            label="GitHub / colenio/jira-cli",
        ),
    )

    assert app._provider_query_placeholder() == (
        'GitHub issue query, e.g. status = "all" AND labels = "bug" ORDER BY updated DESC'
    )


def test_board_column_can_focus_is_false():
    from jira_cli.tui.features.board.widgets import BoardColumn

    assert BoardColumn.can_focus is False


async def test_board_widget_keyboard_navigation(sample_issues):
    client = FakeJiraClient()
    app = JiraApp(client, "A", sample_issues, current_user_display_name="Marcel Körtgen")
    async with app.run_test() as pilot:
        await pilot.press("b")  # toggle board
        selected = app._selected_issue()
        assert selected is not None
        assert selected.status == "To Do"

        await pilot.press("right")
        selected_after_right = app._selected_issue()
        assert selected_after_right is not None
        assert selected_after_right.status == "In Progress"

        await pilot.press("left")
        selected_after_left = app._selected_issue()
        assert selected_after_left is not None
        assert selected_after_left.status == "To Do"


async def test_board_widget_focus_restored_after_command(sample_issues):
    client = FakeJiraClient()
    app = JiraApp(client, "A", sample_issues, current_user_display_name="Marcel Körtgen")
    async with app.run_test() as pilot:
        await pilot.press("b")  # toggle board
        selected_before = app._selected_issue()
        assert selected_before is not None

        await pilot.press("colon")  # open command bar
        await pilot.press("b")
        await pilot.press("enter")
        await pilot.pause()

        selected_after = app._selected_issue()
        assert selected_after is not None
        assert selected_after.key == selected_before.key


async def test_edit_title_updates_selected_issue(sample_issues):
    client = FakeJiraClient()
    app = JiraApp(client, "A", sample_issues, current_user_display_name="Marcel Körtgen")

    async def skip_refresh() -> None:
        return None

    app.action_refresh = skip_refresh

    async with app.run_test():
        app.pending_issue_key = "A-1"
        await app._submit_edit_title("Renamed issue")

    assert client.update_calls == [("A-1", {"summary": "Renamed issue"})]


async def test_action_suggester_completion():
    from jira_cli.tui.features.workflow.suggester import ActionSuggester

    suggester = ActionSuggester(["In Progress", "Done", "Todo"])
    assert await suggester.get_suggestion("in") == "In Progress"
    assert await suggester.get_suggestion("do") == "Done"
    assert await suggester.get_suggestion("In Progress | ") is None
    assert await suggester.get_suggestion("In Progress | do") == "In Progress | Done"


async def test_mention_suggester_preserves_comment_prefix():
    from jira_cli.tui.features.comment.suggester import MentionSuggester

    suggester = MentionSuggester(
        ["LiBar82", "Julian Dannenberg", "mkoertgen"],
        aliases={"Julian Dannenberg": "work-jdannenberg"},
    )
    assert await suggester.get_suggestion("Please review @li") == "Please review @LiBar82"
    assert await suggester.get_suggestion("Please review @jul") == "Please review @work-jdannenberg"
    assert await suggester.get_suggestion("@mko") == "@mkoertgen"
    assert await suggester.get_suggestion("No mention here") is None


async def test_open_issue_works_in_board_mode(sample_issues, monkeypatch):
    client = FakeJiraClient()
    app = JiraApp(
        client,
        "A",
        sample_issues,
        current_user_display_name="Marcel Körtgen",
        context=ProviderContext(name="jira:A", provider="jira", target="A", label="Jira / A"),
    )
    opened_urls = []
    monkeypatch.setattr("webbrowser.open", lambda url: opened_urls.append(url))

    async with app.run_test() as pilot:
        await pilot.press("b")  # toggle board
        await pilot.press("v")  # view / open issue in browser
        assert opened_urls == ["https://example.atlassian.net/browse/A-1"]


async def test_open_issue_ignored_in_demo_mode(sample_issues, monkeypatch):
    client = FakeJiraClient()
    app = JiraApp(
        client,
        "DEMO",
        sample_issues,
        current_user_display_name="Marcel Körtgen",
        context=ProviderContext(name="demo", provider="demo", target="DEMO", label="Demo / DEMO"),
    )
    opened_urls = []
    monkeypatch.setattr("webbrowser.open", lambda url: opened_urls.append(url))

    async with app.run_test() as pilot:
        await pilot.press("v")
        assert opened_urls == []


async def test_edit_modal_escape_does_not_clear_filter(sample_issues):
    client = FakeJiraClient()
    app = JiraApp(client, "A", sample_issues, current_user_display_name="Marcel Körtgen")

    async with app.run_test() as pilot:
        filter_input = app.query_one("#filter_input", Input)
        filter_input.value = "first"
        await app._apply_filter("first")
        await pilot.press("e")
        await pilot.press("escape")

        assert filter_input.value == "first"


async def test_type_quick_filter_runs_server_side(app):
    async with app.run_test() as pilot:
        await app._submit_command("type=bug")
        await pilot.pause()
        assert app.type_filter == "Bug"
        assert app.quick_filter_clauses["type"] == 'issuetype = "Bug"'
        assert [i.key for i in app.issues] == ["A-2"]

        await app._submit_command("clear")
        await pilot.pause()
        assert app.type_filter == ""
        assert app.quick_filter_clauses == {}
        assert len(app.issues) == 5


async def test_status_quick_filter_runs_server_side(app):
    async with app.run_test() as pilot:
        await app._submit_command("status=done")
        await pilot.pause()
        assert app.status_filter == "Done"
        assert [i.key for i in app.issues] == ["A-3"]


async def test_assignee_quick_filter_runs_server_side(app):
    async with app.run_test() as pilot:
        await app._submit_command("assignee=alice")
        await pilot.pause()
        assert app.assignee_filter == "Alice"
        assert [i.key for i in app.issues] == ["A-1", "A-3"]


async def test_assignee_quick_filter_is_umlaut_tolerant(app):
    async with app.run_test() as pilot:
        # ASCII transliteration ("oe") should still match the umlaut form ("ö") in Jira data.
        await app._submit_command("assignee=koertgen")
        await pilot.pause()
        assert app.assignee_filter == "Marcel Körtgen"
        assert [i.key for i in app.issues] == ["A-5"]


async def test_assignee_quick_filter_not_limited_to_loaded_page(sample_issues):
    """The bug this fixes: an issue absent from the currently loaded page must still be found,
    since the filter is a server-side JQL query (plus a server-side assignee lookup for name
    resolution), not a local search over `all_issues`."""
    all_assignees = sorted({i.assignee for i in sample_issues if i.assignee})
    client = FakeJiraClient(assignable_users=all_assignees)
    app = JiraApp(client, "A", [sample_issues[0]], current_user_display_name="Marcel Körtgen")
    app.query.search_custom_jql = make_fake_search_custom_jql(sample_issues, current_user_name="Marcel Körtgen")
    async with app.run_test() as pilot:
        await app._submit_command("assignee=koertgen")
        await pilot.pause()
        assert [i.key for i in app.issues] == ["A-5"]


async def test_assignee_me_shortcut_uses_jql_current_user(app):
    async with app.run_test() as pilot:
        await app._submit_command("assignee=me")
        await pilot.pause()
        assert app.quick_filter_clauses["assignee"] == "assignee = currentUser()"
        assert [i.key for i in app.issues] == ["A-5"]


async def test_label_quick_filter_runs_server_side(app):
    async with app.run_test() as pilot:
        await app._submit_command("label=backend")
        await pilot.pause()
        assert app.label_filter == "backend"
        assert [i.key for i in app.issues] == ["A-2", "A-3"]


async def test_priority_quick_filter_runs_server_side(app):
    async with app.run_test() as pilot:
        await app._submit_command("priority=high")
        await pilot.pause()
        assert app.priority_filter == "High"
        assert app.quick_filter_clauses["priority"] == 'priority = "High"'
        assert [i.key for i in app.issues] == ["A-2"]


async def test_order_command_runs_server_side(app):
    async with app.run_test() as pilot:
        seen_jql = {}
        app.query.search_custom_jql = lambda jql, fields=None, max_results=50: (
            seen_jql.setdefault("jql", jql) and []
        )

        await app._submit_command("order=priority desc")
        await pilot.pause()
        assert app.order_by == "priority desc"
        assert seen_jql["jql"] == "project = A ORDER BY priority DESC"


async def test_me_command_shows_current_user(app):
    async with app.run_test() as pilot:
        await app._submit_command("me")
        await pilot.pause()
        detail = app.query_one("#user_detail")
        assert app.active_kind == "users"
        assert app.query_one("#user_table").display is True
        assert app.query_one("#issue_table").display is False
        assert "marcel@example.com" in detail.render()


async def test_users_command_shows_assignable_users(app):
    async with app.run_test() as pilot:
        await app._submit_command("users")
        await pilot.pause()
        detail = app.query_one("#user_detail")
        assert app.active_kind == "users"
        assert app.query_one("#user_table").display is True
        assert "alice@example.com" in detail.render()


async def test_user_search_command_uses_project_fallback(app):
    async with app.run_test() as pilot:
        await app._submit_command("user=Marcel")
        await pilot.pause()
        detail = app.query_one("#user_detail")
        assert app.active_kind == "users"
        assert "marcel@example.com" in detail.render()


async def test_issue_filter_switches_back_from_users_to_issues(app):
    async with app.run_test() as pilot:
        await app._submit_command("users")
        await app._submit_command("priority=high")
        await pilot.pause()
        assert app.active_kind == "issues"
        assert app.query_one("#issue_table").display is True
        assert app.query_one("#user_table").display is False
        assert [i.key for i in app.issues] == ["A-2"]


async def test_milestones_command_shows_versions(app):
    async with app.run_test() as pilot:
        await app._submit_command("milestones")
        await pilot.pause()
        detail = app.query_one("#version_detail")
        assert app.active_kind == "versions"
        assert app.query_one("#version_table").display is True
        assert app.query_one("#issue_table").display is False
        assert "2026.09" in detail.render()


async def test_labels_command_shows_label_resource(app):
    async with app.run_test() as pilot:
        await app._submit_command("labels")
        await pilot.pause()
        detail = app.query_one("#label_detail")
        assert app.active_kind == "labels"
        assert app.query_one("#label_table").display is True
        assert app.query_one("#issue_table").display is False
        assert "backend" in detail.render()


async def test_key_quick_filter_jumps_to_exact_issue(app):
    async with app.run_test() as pilot:
        await app._submit_command("key=a-5")
        await pilot.pause()
        assert app.key_filter == "A-5"
        assert [i.key for i in app.issues] == ["A-5"]


async def test_bare_command_resolves_across_dimensions(app):
    async with app.run_test() as pilot:
        # "bob" only matches an assignee, sofka-palette style bare lookup
        await app._submit_command("bob")
        await pilot.pause()
        assert app.assignee_filter == "Bob"
        assert [i.key for i in app.issues] == ["A-2"]


async def test_unknown_command_leaves_filters_untouched(app):
    async with app.run_test() as pilot:
        await app._submit_command("nonexistent-value")
        await pilot.pause()
        assert app.type_filter == app.status_filter == app.assignee_filter == app.label_filter == ""
        assert len(app.issues) == 5


async def test_command_bar_switches_views(app):
    async with app.run_test() as pilot:
        await app._submit_command("board")
        await pilot.pause()
        assert app.board_visible is True

        await app._submit_command("table")
        await pilot.pause()
        assert app.board_visible is False


async def test_overdue_command_runs_expected_jql(app):
    async with app.run_test() as pilot:
        seen_jql = {}
        app.query.search_custom_jql = lambda jql, fields=None, max_results=50: (
            seen_jql.setdefault("jql", jql) and []
        )

        await app._submit_command("overdue")
        await pilot.pause()
        assert seen_jql["jql"] == "project = A AND duedate < now() AND statusCategory != Done ORDER BY duedate ASC"


async def test_overdue_mine_command_adds_current_user_clause(app):
    async with app.run_test() as pilot:
        seen_jql = {}
        app.query.search_custom_jql = lambda jql, fields=None, max_results=50: (
            seen_jql.setdefault("jql", jql) and []
        )

        await app._submit_command("overdue=me")
        await pilot.pause()
        assert "assignee = currentUser()" in seen_jql["jql"]


async def test_drill_down_uses_local_subtask_keys_when_known(app):
    async with app.run_test() as pilot:
        seen_jql = {}
        app.query.search_custom_jql = lambda jql, fields=None, max_results=50: (
            seen_jql.setdefault("jql", jql) and []
        )

        table = app.query_one("#issue_table")
        table.replace_rows(
            [IssueRow(key="A-1", summary="First", issue_type="Story", child_keys=["A-2", "A-3"])]
        )
        await pilot.pause()

        await app.action_drill_down()
        await pilot.pause()
        assert seen_jql["jql"] == "key in (A-2,A-3) ORDER BY key"


async def test_drill_down_falls_back_to_parent_query_for_epics(app):
    """Epics have no local child_keys (those only reflect Jira's 'subtasks' field); drilling
    down must still work via a server-side 'parent = <key>' query."""
    async with app.run_test() as pilot:
        epic_children = [IssueRow(key="A-9", summary="Epic child", issue_type="Story", status="To Do")]
        app.query.search_custom_jql = lambda jql, fields=None, max_results=50: (
            epic_children if jql == "parent = COM-12 ORDER BY key" else []
        )

        table = app.query_one("#issue_table")
        table.replace_rows([IssueRow(key="COM-12", summary="Epic", issue_type="Epic")])
        await pilot.pause()

        await app.action_drill_down()
        await pilot.pause()
        assert [i.key for i in app.issues] == ["A-9"]


async def test_quick_filters_combine(app):
    async with app.run_test() as pilot:
        await app._submit_command("label=backend")  # -> backend (A-2, A-3)
        await app._submit_command("type=bug")  # -> Bug
        await pilot.pause()
        assert app.label_filter == "backend"
        assert app.type_filter == "Bug"
        assert [i.key for i in app.issues] == ["A-2"]


async def test_board_toggle_keeps_selection_in_sync(app):
    async with app.run_test() as pilot:
        app.action_toggle_board()
        await pilot.pause()
        assert app.board_visible is True

        board = app.query_one("#issue_board", BoardWidget)
        selected = app._selected_issue()
        assert selected is not None
        assert selected.key == board.get_selected_issue().key

        app.action_toggle_board()
        await pilot.pause()
        assert app.board_visible is False
        assert app._selected_issue() is not None


async def test_board_reflects_active_filters(app):
    async with app.run_test() as pilot:
        await app._submit_command("status=done")  # -> Done (A-3 only)
        app.action_toggle_board()
        await pilot.pause()

        board = app.query_one("#issue_board", BoardWidget)
        assert [i.key for i in board.all_issues] == ["A-3"]


def test_board_orders_backlog_first_and_done_last():
    issues = [
        IssueRow(key="A-1", summary="Done", status="Done"),
        IssueRow(key="A-2", summary="Custom", status="QA"),
        IssueRow(key="A-3", summary="Backlog", status="Backlog"),
    ]

    assert list(group_by_status(issues)) == ["Backlog", "QA", "Done"]
