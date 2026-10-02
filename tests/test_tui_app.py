"""Tests for the interactive Jira TUI (JiraApp), driven headlessly via Textual's pilot."""

import pytest
from textual.widgets import DataTable, Input

from jira_cli.models import IssueRow
from jira_cli.providers import ProviderContext, ProviderDescriptor, ResourceDescriptor
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
        self.assignable_user_requests: list[int] = []

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
        self.assignable_user_requests.append(max_results)
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


async def test_version_rows_use_sprint_closed_and_future_styles(app):
    async with app.run_test():
        table = app.query_one("#version_table")
        table.replace_rows(
            [
                {"id": "released", "name": "v1.0", "released": True},
                {"id": "unreleased", "name": "v2.0", "released": False},
            ]
        )

        assert str(table.get_row("released")[0].style) == "dim"
        assert str(table.get_row("unreleased")[0].style) == "bold cyan"


async def test_demo_version_theme_color_refreshes_after_release_change():
    from jira_cli.demo import DEMO_PROJECT_KEY
    from jira_cli.providers.demo import DemoProvider
    from jira_cli.query import JiraQuery

    client = DemoProvider()
    issues = JiraQuery(client).search_project(DEMO_PROJECT_KEY, max_results=100)
    demo_app = JiraApp(client, DEMO_PROJECT_KEY, issues, current_user_display_name="Marcel Körtgen")
    demo_app._children_prefetch.prefetch = lambda issue: None

    async with demo_app.run_test() as pilot:
        await pilot.pause()
        table = demo_app.query_one("#version_table")
        demo_app._show_versions("Versions")
        await pilot.pause()
        assert str(table.get_row("demo-v050")[0].style) == "bright_cyan"

        try:
            client.update_version(DEMO_PROJECT_KEY, "v0.5.0", released=True)
            demo_app._show_versions("Versions")
            await pilot.pause()
            assert str(table.get_row("demo-v050")[0].style) == "dim"
        finally:
            client.update_version(DEMO_PROJECT_KEY, "v0.5.0", released=False)


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


async def test_provider_declared_resource_opens_in_generic_table(sample_issues):
    class ResourceClient(FakeJiraClient):
        def describe(self) -> ProviderDescriptor:
            return ProviderDescriptor(
                name="fake",
                resources=(
                    ResourceDescriptor(kind="components", fields=("name", "lead")),
                    ResourceDescriptor(kind="sprints", fields=("name", "state", "board")),
                ),
            )

        def list_resource(self, kind: str, project_key: str) -> list[dict]:
            assert project_key == "A"
            if kind == "components":
                return [
                    {"name": "Platform", "lead": "Ada", "themeColor": "bright_magenta"},
                    {"name": "Storage", "lead": "Lin"},
                ]
            return [
                {"name": "Active Sprint", "state": "active", "board": "Scrum"},
                {"name": "Closed Sprint", "state": "closed", "board": "Scrum"},
            ]

    resource_app = JiraApp(ResourceClient(), "A", sample_issues, current_user_display_name="Marcel Körtgen")
    resource_app._children_prefetch.prefetch = lambda issue: None
    async with resource_app.run_test() as pilot:
        await resource_app._submit_command("components")
        await pilot.pause()

        table = resource_app.query_one("#provider_resource_table")
        detail = resource_app.query_one("#provider_resource_detail")
        workspace = resource_app.query_one("#issue_workspace")
        assert resource_app.active_kind == "components"
        assert table.display
        assert detail.display
        assert table.region.y == workspace.region.y
        assert detail.region.y == workspace.region.y
        assert detail.region.x > table.region.x
        assert table.resource_rows[0]["name"] == "Platform"
        assert detail.resource["name"] == "Platform"
        assert str(table.get_row("Platform")[0].style) == "bright_magenta"
        assert resource_app.query_one("#resource-tab-components").label == "Components"
        resource_app.action_focus_command()
        assert "components" in resource_app.query_one("#query_input").placeholder
        assert await resource_app.command_suggester.get_suggestion("comp") == "components"
        resource_app._hide_query_input()

        await pilot.press("down")
        await pilot.pause()
        assert detail.resource["name"] == "Storage"

        await pilot.click("#resource-tab-sprints")
        await pilot.pause()
        assert resource_app.active_kind == "sprints"
        assert len(table.resource_rows) == 2
        await resource_app._apply_filter("active")
        assert [row["name"] for row in table.resource_rows] == ["Active Sprint"]
        assert detail.resource["state"] == "active"


async def test_provider_resources_navigate_to_issues_or_empty_list(sample_issues):
    class CatalogClient(FakeJiraClient):
        def describe(self) -> ProviderDescriptor:
            return ProviderDescriptor(
                name="fake",
                resources=(
                    ResourceDescriptor(kind="sprints", fields=("name", "state")),
                    ResourceDescriptor(kind="components", fields=("name",)),
                ),
            )

        def list_resource(self, kind: str, project_key: str) -> list[dict]:
            if kind == "sprints":
                return [
                    {"id": 42, "name": "Sprint 42", "state": "active"},
                    {"id": 43, "name": "Sprint 43", "state": "future"},
                    {"id": 41, "name": "Sprint 41", "state": "closed"},
                ]
            return [{"id": "7", "name": "Platform"}]

        def resource_issue_query(self, kind: str, resource: dict, project_key: str) -> str | None:
            return f"project = {project_key} AND sprint = {resource['id']}" if kind == "sprints" else None

    sprint_issue = IssueRow(key="A-42", summary="In sprint", issue_type="Story")
    nav_app = JiraApp(CatalogClient(), "A", sample_issues, current_user_display_name="Marcel Körtgen")
    nav_app._children_prefetch.prefetch = lambda issue: None
    seen_jql = []
    nav_app.query.search_custom_jql = lambda jql, fields=None, max_results=50: seen_jql.append(jql) or [sprint_issue]
    async with nav_app.run_test() as pilot:
        await nav_app._submit_command("sprints")
        await pilot.pause()
        sprint_table = nav_app.query_one("#provider_resource_table")
        assert str(sprint_table.get_row("42")[0].style) == "bold green"
        assert str(sprint_table.get_row("43")[0].style) == "cyan"
        assert str(sprint_table.get_row("41")[0].style) == "dim"
        assert nav_app.check_action("issues_for_resource", ())
        assert "related" in nav_app._command_verbs()
        await pilot.press("i")
        await pilot.pause()
        assert seen_jql == ["project = A AND sprint = 42"]
        assert nav_app.active_kind == "issues"
        assert [issue.key for issue in nav_app.issues] == ["A-42"]

        await nav_app._submit_command("components")
        await pilot.pause()
        await nav_app._submit_command("related")
        await pilot.pause()
        assert seen_jql == ["project = A AND sprint = 42"]
        assert nav_app.active_kind == "issues"
        assert nav_app.issues == []


async def test_users_versions_and_labels_use_horizontal_master_detail(app):
    app._children_prefetch.prefetch = lambda issue: None
    views = {
        "users": ("user_table", "user_detail"),
        "versions": ("version_table", "version_detail"),
        "labels": ("label_table", "label_detail"),
    }

    async with app.run_test() as pilot:
        for kind, (table_id, detail_id) in views.items():
            await pilot.click(f"#resource-tab-{kind}")
            await pilot.pause()

            table = app.query_one(f"#{table_id}")
            detail = app.query_one(f"#{detail_id}")
            workspace = app.query_one("#issue_workspace")
            assert table.display
            assert detail.display
            assert table.region.y == workspace.region.y
            assert detail.region.y == workspace.region.y
            assert detail.region.x > table.region.x


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


async def test_timeline_toggle_shows_timeline_view(app):
    async with app.run_test() as pilot:
        await pilot.press("g")
        assert app.timeline_visible is True
        assert app.query_one("#issue_timeline").display is True
        assert app.query_one("#issue_table").display is False
        await pilot.press("g")
        assert app.timeline_visible is False


async def test_demo_provider_renders_epic_timeline_bars():
    from jira_cli.demo import DEMO_PROJECT_KEY
    from jira_cli.providers.demo import DemoProvider
    from jira_cli.query import JiraQuery

    client = DemoProvider()
    issues = JiraQuery(client).search_project(DEMO_PROJECT_KEY, max_results=100)
    demo_app = JiraApp(client, DEMO_PROJECT_KEY, issues, current_user_display_name="Marcel Körtgen")
    demo_app._children_prefetch.prefetch = lambda issue: None

    async with demo_app.run_test() as pilot:
        await pilot.press("g")
        await pilot.pause()

        timeline = demo_app.query_one("#issue_timeline")
        table = timeline.query_one("#timeline_table", DataTable)
        row = table.get_row("DEMO-10")
        assert timeline._unit == "sprint"
        assert any(bool(str(cell)) for cell in row[2:])
        headers = [str(column.label) for column in table.columns.values()]
        assert "▶ Sprint 3 (DEMO Scrum)" in headers
        focus = type(timeline).focus_period_index(timeline._periods)
        assert timeline._periods[focus].state == "active"
        assert "bold" in str(row[0].style)


async def test_timeline_renders_non_epic_provider_plan_items(sample_issues):
    from datetime import date

    from jira_cli.timeline import TimelineItem

    class MilestoneClient(FakeJiraClient):
        def list_timeline_items(self, project_key: str) -> list[TimelineItem]:
            return [
                TimelineItem(
                    key="repo#M4",
                    title="0.7.0",
                    start=date(2026, 9, 1),
                    end=date(2026, 12, 31),
                    issue_type="Milestone",
                    target_url="https://github.com/acme/repo/milestone/4",
                )
            ]

        def list_timeline_markers(self, project_key: str) -> list:
            return []

    milestone_app = JiraApp(MilestoneClient(), "A", sample_issues, current_user_display_name="Marcel Körtgen")
    milestone_app._children_prefetch.prefetch = lambda issue: None
    async with milestone_app.run_test() as pilot:
        await pilot.press("g")
        await pilot.pause()

        timeline = milestone_app.query_one("#issue_timeline")
        table = timeline.query_one("#timeline_table", DataTable)
        row = table.get_row("repo#M4")
        assert str(row[0]) == "Milestone repo#M4"
        assert any(bool(str(cell)) for cell in row[2:])


async def test_timeline_uses_provider_sprint_intervals(sample_issues):
    from jira_cli.models import IssueRow

    class SprintClient(FakeJiraClient):
        def describe(self) -> ProviderDescriptor:
            return ProviderDescriptor(
                name="fake",
                resources=(ResourceDescriptor(kind="sprints", fields=("name", "startDate", "endDate")),),
            )

        def list_resource(self, kind: str, project_key: str) -> list[dict]:
            assert (kind, project_key) == ("sprints", "A")
            return [
                {"id": "1", "name": "Sprint 1", "state": "closed", "startDate": "2026-09-01", "endDate": "2026-09-14"},
                {"id": "2", "name": "Sprint 2", "state": "active", "startDate": "2026-09-15", "endDate": "2026-09-28"},
                {"id": "3", "name": "Sprint 3", "state": "future", "startDate": "2026-09-29", "endDate": "2026-10-12"},
            ]

        def list_epic_sprint_assignments(self, project_key: str) -> dict[str, list[str]]:
            assert project_key == "A"
            return {"A-EPIC": ["2"]}

    epic = IssueRow(
        key="A-EPIC",
        summary="Timeline Epic",
        issue_type="Epic",
    )
    sprint_app = JiraApp(SprintClient(), "A", [epic], current_user_display_name="Marcel Körtgen")
    sprint_app._children_prefetch.prefetch = lambda issue: None
    async with sprint_app.run_test() as pilot:
        await pilot.press("g")
        await pilot.pause()

        timeline = sprint_app.query_one("#issue_timeline")
        assert timeline._unit == "sprint"
        assert [period.label for period in timeline._periods] == ["Sprint 2", "Sprint 3"]
        row = timeline.query_one("#timeline_table", DataTable).get_row("A-EPIC")
        assert [bool(str(cell)) for cell in row[2:]] == [True, False]
        headers = [str(column.label) for column in timeline.query_one("#timeline_table", DataTable).columns.values()]
        assert headers[2] == "▶ Sprint 2"
        assert headers[3] == "Sprint 3"
        assert type(timeline).focus_period_index(timeline._periods) == 0
        assert "bold" in str(row[0].style)
        timeline.action_cycle_granularity()
        assert timeline._unit == "week"
        timeline.set_granularity("sprint")
        assert timeline._unit == "sprint"


async def test_timeline_sprint_scale_falls_back_without_provider_sprints(sample_issues):
    from jira_cli.models import IssueRow

    epic = IssueRow(
        key="A-EPIC",
        summary="Timeline Epic",
        issue_type="Epic",
        start_date="2026-09-10",
        due_date="2026-10-02",
    )
    fallback_app = JiraApp(FakeJiraClient(), "A", [epic], current_user_display_name="Marcel Körtgen")
    fallback_app._children_prefetch.prefetch = lambda issue: None
    async with fallback_app.run_test() as pilot:
        await pilot.press("g")
        timeline = fallback_app.query_one("#issue_timeline")
        timeline.set_granularity("sprint")
        assert timeline._unit == "week"


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


def test_issue_detail_uses_markdown_separators_between_sections(sample_issues):
    from jira_cli.tui.features.issues.widgets import IssueDetailWidget

    widget = IssueDetailWidget()
    widget.issue = sample_issues[0]
    widget.comment_text = "**@reviewer**\n\nLooks good"
    widget.comment_position = "1/1"

    rendered = widget._render_body()

    assert rendered.count("\n\n---\n\n") == 3
    assert rendered.index("Type:") < rendered.index("No description provided")
    assert rendered.index("No description provided") < rendered.index("Comments")


async def test_action_suggester_completion():
    from jira_cli.tui.features.workflow.suggester import ActionSuggester

    suggester = ActionSuggester(["In Progress", "Done", "Todo"])
    assert await suggester.get_suggestion("in") == "In Progress"
    assert await suggester.get_suggestion("do") == "Done"
    assert await suggester.get_suggestion("In Progress | ") is None
    assert await suggester.get_suggestion("In Progress | do") == "In Progress | Done"


async def test_edit_modal_adds_and_removes_labels_with_multiselect(sample_issues):
    from jira_cli.tui.features.issues.modals import EditIssueModal
    from textual.widgets import SelectionList

    app = JiraApp(FakeJiraClient(), "A", sample_issues, current_user_display_name="Marcel Körtgen")
    async with app.run_test() as pilot:
        app.push_screen(
            EditIssueModal(
                "A-1",
                "Title",
                labels="backend, frontend",
                label_candidates=["backend", "documentation", "frontend"],
            )
        )
        await pilot.pause()
        labels = app.screen.query_one("#edit_labels", SelectionList)
        assert set(labels.selected) == {"backend", "frontend"}

        labels.focus()
        labels.highlighted = 0
        await pilot.press("space")
        labels.highlighted = 1
        await pilot.press("space")

        assert set(labels.selected) == {"documentation", "frontend"}


async def test_edit_modal_filters_labels_and_keeps_tab_navigation(sample_issues):
    from jira_cli.tui.features.issues.modals import EditIssueModal
    from textual.widgets import Input, SelectionList

    app = JiraApp(FakeJiraClient(), "A", sample_issues, current_user_display_name="Marcel Körtgen")
    async with app.run_test() as pilot:
        app.push_screen(
            EditIssueModal(
                "A-1",
                "Title",
                labels="backend",
                label_candidates=["backend", "documentation", "frontend"],
            )
        )
        await pilot.pause()
        label_filter = app.screen.query_one("#label_filter", Input)
        label_filter.focus()
        label_filter.value = "doc"
        await pilot.pause()

        labels = app.screen.query_one("#edit_labels", SelectionList)
        assert [option.value for option in labels.options] == ["documentation"]
        await pilot.press("tab")
        assert app.screen.focused is labels


def test_label_catalog_is_loaded_once(sample_issues):
    client = FakeJiraClient()
    calls = 0
    original = client.list_labels

    def counted_list_labels(project_key: str):
        nonlocal calls
        calls += 1
        return original(project_key)

    client.list_labels = counted_list_labels
    app = JiraApp(client, "A", sample_issues, current_user_display_name="Marcel Körtgen")

    assert app._label_names() == ["backend", "frontend"]
    assert app._label_names() == ["backend", "frontend"]
    assert calls == 1


def test_issue_actions_are_hidden_outside_issue_view(sample_issues):
    app = JiraApp(FakeJiraClient(), "A", sample_issues, current_user_display_name="Marcel Körtgen")

    app.active_kind = "labels"

    assert app.check_action("focus_command", ()) is True
    assert app.check_action("refresh", ()) is True
    assert app.check_action("focus_find", ()) is False
    assert app.check_action("open_issue", ()) is False
    assert app.check_action("comment", ()) is False


def test_label_management_actions_follow_provider_descriptor(sample_issues):
    from jira_cli.providers import ActionDescriptor, ResourceDescriptor

    client = FakeJiraClient()
    client.describe = lambda: ProviderDescriptor(
        name="fake",
        resources=(ResourceDescriptor(kind="labels", actions=(ActionDescriptor(name="create"),)),),
    )
    app = JiraApp(client, "A", sample_issues, current_user_display_name="Marcel Körtgen")
    app.active_kind = "labels"

    assert app.check_action("create_resource", ()) is True
    assert app.check_action("edit_resource", ()) is False
    assert app.check_action("delete_resource", ()) is False


def test_new_action_follows_resource_create_capability(sample_issues):
    from jira_cli.providers import ActionDescriptor, ResourceDescriptor

    client = FakeJiraClient()
    client.describe = lambda: ProviderDescriptor(
        name="fake",
        resources=(
            ResourceDescriptor(kind="issues", actions=(ActionDescriptor(name="create"),)),
            ResourceDescriptor(kind="labels", actions=(ActionDescriptor(name="create"),)),
            ResourceDescriptor(kind="versions", actions=(ActionDescriptor(name="create"),)),
        ),
    )
    app = JiraApp(client, "A", sample_issues, current_user_display_name="Marcel Körtgen")

    for kind in ("issues", "labels", "versions"):
        app.active_kind = kind
        assert app.check_action("create_resource", ()) is True

    app.active_kind = "users"
    assert app.check_action("create_resource", ()) is False

    visible_keys = [binding.key for binding in JiraApp.BINDINGS if binding.show]
    assert visible_keys.index("n") < visible_keys.index("ctrl+t")


async def test_mention_suggester_preserves_comment_prefix():
    from jira_cli.tui.features.comment.suggester import MentionSuggester

    suggester = MentionSuggester(
        ["LiBar82", "Julian Dannenberg", "mkoertgen"],
        aliases={"Julian Dannenberg": "work-jdannenberg"},
    )
    assert await suggester.get_suggestion("Please review @li") == "Please review @LiBar82"
    assert await suggester.get_suggestion("Please review @jul") == "Please review @work-jdannenberg"
    assert await suggester.get_suggestion("Please review @Julian D") == "Please review @work-jdannenberg"
    assert await suggester.get_suggestion("@mko") == "@mkoertgen"
    assert await suggester.get_suggestion("No mention here") is None


async def test_comment_thread_is_focusable_and_tabbable(sample_issues):
    from jira_cli.tui.features.issues.modals import CommentModal, CommentThreadMarkdown
    from textual.widgets import TextArea

    app = JiraApp(FakeJiraClient(), "A", sample_issues, current_user_display_name="Marcel Körtgen")
    async with app.run_test() as pilot:
        app.push_screen(CommentModal("A-1", "\n\n".join(f"Comment {index}" for index in range(30))))
        await pilot.pause()

        assert isinstance(app.screen.focused, CommentThreadMarkdown)
        await pilot.press("tab")
        assert isinstance(app.screen.focused, TextArea)
        await pilot.press("shift+tab")
        assert isinstance(app.screen.focused, CommentThreadMarkdown)

        bracket_bindings = {binding.key: binding.action for binding in CommentThreadMarkdown.BINDINGS}
        assert bracket_bindings["pageup,left_square_bracket,p"] == "page_up"
        assert bracket_bindings["pagedown,right_square_bracket,n"] == "page_down"

        app_binding_keys = {binding.key for binding in JiraApp.BINDINGS}
        assert "left_square_bracket" not in app_binding_keys
        assert "right_square_bracket" not in app_binding_keys


async def test_comment_editor_completes_mentions_with_tab(sample_issues):
    from jira_cli.tui.features.issues.modals import CommentModal
    from textual.widgets import Label, TextArea

    app = JiraApp(FakeJiraClient(), "A", sample_issues, current_user_display_name="Marcel Körtgen")
    async with app.run_test() as pilot:
        app.push_screen(
            CommentModal(
                "A-1",
                "No comments yet",
                mention_users=[{"displayName": "Julian Dannenberg", "accountId": "work-jdannenberg"}],
            )
        )
        await pilot.pause()
        await pilot.press("tab")
        editor = app.screen.query_one("#comment_editor", TextArea)
        editor.load_text("Please review @jul")
        editor.move_cursor((0, len(editor.text)))
        editor.post_message(TextArea.Changed(editor))
        await pilot.pause()

        suggestion = app.screen.query_one("#mention_suggestion", Label)
        assert "Julian Dannenberg" in str(suggestion.render())

        await pilot.press("tab")
        assert editor.text == "Please review @work-jdannenberg"


async def test_comment_mentions_load_all_users_once(sample_issues):
    client = FakeJiraClient(assignable_users=["Andreas Bauer", "Tobias Braun"])
    app = JiraApp(client, "A", sample_issues, current_user_display_name="Marcel Körtgen")

    async with app.run_test() as pilot:
        app.action_comment()
        await pilot.pause()
        await app.pop_screen()
        app.action_comment()
        await pilot.pause()

    assert client.assignable_user_requests == [1000]


async def test_comment_editor_completes_display_name_with_space(sample_issues):
    from jira_cli.tui.features.issues.modals import CommentModal
    from textual.widgets import Label, TextArea

    app = JiraApp(FakeJiraClient(), "A", sample_issues, current_user_display_name="Marcel Körtgen")
    async with app.run_test() as pilot:
        app.push_screen(
            CommentModal(
                "A-1",
                "No comments yet",
                mention_users=[{"displayName": "Julian Dannenberg", "accountId": "work-jdannenberg"}],
            )
        )
        await pilot.pause()
        await pilot.press("tab")
        editor = app.screen.query_one("#comment_editor", TextArea)
        editor.load_text("Please review @Julian D")
        editor.move_cursor((0, len(editor.text)))
        editor.post_message(TextArea.Changed(editor))
        await pilot.pause()

        assert "Julian Dannenberg" in str(app.screen.query_one("#mention_suggestion", Label).render())
        await pilot.press("tab")
        assert editor.text == "Please review @work-jdannenberg"


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


async def test_users_view_uses_complete_sorted_cache_and_includes_current_user(sample_issues):
    client = FakeJiraClient(assignable_users=["Tobias Braun", "Andreas Bauer"])
    app = JiraApp(client, "A", sample_issues, current_user_display_name="Marcel Körtgen")

    async with app.run_test() as pilot:
        await app._submit_command("users")
        await pilot.pause()

        table = app.query_one("#user_table")
        assert [user["displayName"] for user in table.users] == [
            "Andreas Bauer",
            "Marcel Körtgen",
            "Tobias Braun",
        ]
        assert client.assignable_user_requests == [1000]


async def test_slash_filter_in_users_view_filters_users_and_resolves_me(sample_issues):
    client = FakeJiraClient(assignable_users=["Tobias Braun", "Andreas Bauer"])
    app = JiraApp(client, "A", sample_issues, current_user_display_name="Marcel Körtgen")

    async with app.run_test() as pilot:
        app._show_assignable_users()
        await app._apply_filter("tobias")
        await pilot.pause()
        assert [user["displayName"] for user in app.query_one("#user_table").users] == ["Tobias Braun"]

        await app._apply_filter("me")
        await pilot.pause()
        assert [user["displayName"] for user in app.query_one("#user_table").users] == ["Marcel Körtgen"]


def test_theme_toggle_switches_light_and_dark(sample_issues):
    app = JiraApp(FakeJiraClient(), "A", sample_issues, current_user_display_name="Marcel Körtgen")

    app.theme = "textual-dark"
    app.action_toggle_theme()
    assert app.theme == "textual-light"
    app.action_toggle_theme()
    assert app.theme == "textual-dark"


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


async def test_jql_command_keeps_equals_signs_and_replaces_rows(app):
    epic = IssueRow(key="A-9", summary="Only epic", issue_type="Epic")
    async with app.run_test() as pilot:
        seen_jql = {}
        app.query.search_custom_jql = lambda jql, fields=None, max_results=50: (
            seen_jql.setdefault("jql", jql) and [epic]
        )

        await app._submit_command('jql project = A AND issuetype = "Epic"')
        await pilot.pause()
        assert seen_jql["jql"] == 'project = A AND issuetype = "Epic"'
        assert [issue.key for issue in app.issues] == ["A-9"]


async def test_jql_filters_rows_when_provider_declares_issues_resource(sample_issues):
    class IssuesDescriptorClient(FakeJiraClient):
        def describe(self) -> ProviderDescriptor:
            return ProviderDescriptor(
                name="fake",
                query_language="JQL",
                resources=(
                    ResourceDescriptor(kind="issues", fields=("key", "summary")),
                    ResourceDescriptor(kind="sprints", fields=("name",)),
                ),
            )

        def list_resource(self, kind: str, project_key: str) -> list[dict]:
            raise AssertionError(f"issue views must not load catalog '{kind}'")

    epic = IssueRow(key="A-9", summary="Only epic", issue_type="Epic")
    jql_app = JiraApp(IssuesDescriptorClient(), "A", sample_issues, current_user_display_name="Marcel Körtgen")
    jql_app._children_prefetch.prefetch = lambda issue: None
    jql_app.query.search_custom_jql = lambda jql, fields=None, max_results=50: [epic]
    async with jql_app.run_test() as pilot:
        await jql_app._submit_command('jql project = A AND issuetype = "Epic"')
        await pilot.pause()
        assert [issue.key for issue in jql_app.issues] == ["A-9"]
        assert jql_app.query_one("#issue_table").row_count == 1

        await jql_app.action_refresh()
        await pilot.pause()
        assert [issue.key for issue in jql_app.issues] == ["A-9"]


async def test_j_key_opens_jql_input(app):
    async with app.run_test() as pilot:
        await pilot.press("j")
        await pilot.pause()
        assert app.input_mode == "jql"
        assert app.query_one("#query_input").display


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
