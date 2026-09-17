"""Main Textual application for interactive Jira issue management."""

import logging
import webbrowser
from typing import Literal

from rich.markup import escape
from textual.app import ComposeResult, App
from textual.containers import Horizontal, Vertical
from textual.widgets import Label, DataTable, Footer, Input, ListView
from textual.binding import Binding

from jira_cli.models import IssueRow
from jira_cli.providers import IssueTrackerProvider, ProviderContext
from jira_cli.query import JiraQuery, order_by_clause
from jira_cli.quick_filters import QuickFilterResolver, normalize_for_match
from jira_cli.tui.features.board import BoardWidget
from jira_cli.tui.features.board.service import DEFAULT_STATUS_ORDER
from jira_cli.tui.features.comment import JiraCommentFeature
from jira_cli.tui.features.issues import IssueDetailWidget, IssueTableWidget
from jira_cli.tui.features.issues.modals import CommentModal
from jira_cli.tui.features.issues.prefetch import IssueChildrenPrefetch
from jira_cli.tui.features.timeline import TimelineItem, TimelineMarker, TimelineWidget
from jira_cli.tui.controllers.resource_actions import ResourceActionsMixin
from jira_cli.tui.controllers.view_controller import ViewControllerMixin
from jira_cli.tui.controllers.query_controller import QueryControllerMixin
from jira_cli.tui.controllers.workflow_controller import WorkflowControllerMixin
from jira_cli.tui.controllers.resource_views import ResourceViewsMixin
from jira_cli.tui.controllers.issue_controller import IssueControllerMixin
from jira_cli.tui.features.labels import LabelDetailWidget, LabelTableWidget, list_project_labels
from jira_cli.tui.features.query.service import (
    QueryMode,
    QUICK_FILTER_DIMENSIONS,
    build_query_labels,
    filter_issues,
    parse_command,
    resolve_bare_quick_filter,
    run_remote_query,
)
from jira_cli.tui.features.query.suggester import CommandSuggester
from jira_cli.tui.features.users import UserDetailWidget, UserTableWidget, search_project_users
from jira_cli.tui.features.users.modals import UserIssuesModal
from jira_cli.tui.features.versions import VersionDetailWidget, VersionTableWidget, list_project_versions
from jira_cli.tui.features.workflow import JiraWorkflowFeature
from jira_cli.tui.features.workflow.suggester import ActionSuggester
from jira_cli.tui.header import JiraTopBar
from jira_cli.tui.logging import configure_tui_logging, tui_logger

ResourceKind = Literal["issues", "users", "versions", "labels"]


class JiraApp(ResourceActionsMixin, ResourceViewsMixin, IssueControllerMixin, ViewControllerMixin, QueryControllerMixin, WorkflowControllerMixin, App):
    """Main Jira TUI Application."""

    BINDINGS = [
        Binding("q", "quit", "Quit", show=True),
        Binding("p", "reset_source", "Project", show=True),
        Binding("slash", "focus_filter", "Filter", show=True),
        Binding("f", "focus_find", "Find", show=True),
        Binding("colon", "focus_command", "Command", show=True),
        Binding("n", "create_resource", "New", show=True),
        Binding("ctrl+t", "toggle_theme", "Theme", show=True),
        Binding("b", "toggle_board", "Board", show=True),
        Binding("g", "toggle_timeline", "Timeline", show=True),
        Binding("v", "open_issue", "View in Web", show=True),
        Binding("o", "open_issue", "Open in Browser", show=False),
        Binding("insert", "create_resource", "New", show=False),
        Binding("delete", "delete_resource", "Delete", show=True),
        Binding("i", "issues_for_resource", "Issues", show=True),
        Binding("t", "transition", "Transition", show=False),
        Binding("a", "assign", "Assign", show=False),
        Binding("e", "edit_resource", "Edit", show=False),
        Binding("c", "comment", "Comment", show=False),
        Binding("u", "drill_up", "Parent", show=False),
        Binding("d", "drill_down", "Children", show=False),
        Binding("r", "refresh", "Refresh", show=True),
        Binding("question_mark", "help", "Help", show=True),
        Binding("escape", "clear_filter", "Clear Filter", show=False),
    ]

    def notify(self, message: str, *, title: str = "", severity="information", timeout=None, markup: bool = True) -> None:
        """Show a toast and persist its full text when TUI logging is enabled."""
        logger = tui_logger()
        if logger.handlers:
            level = {"error": logging.ERROR, "warning": logging.WARNING}.get(str(severity), logging.INFO)
            logger.log(level, "Toast%s: %s", f" [{title}]" if title else "", message)
        super().notify(message, title=title, severity=severity, timeout=timeout, markup=markup)

    CSS = """
    Screen {
        layout: vertical;
    }

    #issue_table {
        height: 1fr;
    }

    #issue_board {
        height: 1fr;
    }

    #issue_workspace {
        height: 1fr;
    }

    #issue_actions_bar {
        height: auto;
        padding: 0 1;
        background: $surface;
        color: $text-muted;
    }

    #issue_master {
        width: 2fr;
        height: 1fr;
    }

    #issue_workspace > #issue_detail {
        width: 1fr;
        height: 1fr;
    }

    #user_table {
        height: 1fr;
    }

    #version_table {
        height: 1fr;
    }

    #label_table {
        height: 1fr;
    }

    #filter_input {
        display: none;
    }

    #query_input {
        display: none;
    }

    #query_context {
        color: $text-muted;
    }

    #mode_context {
        color: $accent;
    }

    IssueDetailWidget {
        height: 1fr;
        overflow-y: auto;
    }
    """

    def __init__(
        self,
        client: IssueTrackerProvider,
        project_key: str,
        issues: list[IssueRow],
        current_user_display_name: str = "",
        context: ProviderContext | None = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.client = client
        self.project_key = project_key
        self.context = context or ProviderContext(name=f"jira:{project_key}", provider="jira", target=project_key, label=f"Jira / {project_key}")
        self.all_issues = issues
        self.issues = issues
        self.users: list[dict] = []
        self._mention_users: list[dict] | None = None
        self.versions: list[dict] = []
        self.labels: list[dict] = []
        self._labels_loaded = False
        self.query_language = self.client.describe().query_language
        self.current_user_display_name = current_user_display_name
        self.query = JiraQuery(client)
        self._children_prefetch = IssueChildrenPrefetch(
            self.query,
            self.context.provider,
            self.run_worker,
            self.call_from_thread,
            self._selected_issue,
            self.update_issue_detail,
        )
        self.quick_filter_resolver = QuickFilterResolver(client, project_key)
        self.query_mode: QueryMode = "project"
        self.query_expression = ""
        self.last_find_expression = ""
        self.last_jql_expression = ""
        self.type_filter = ""
        self.status_filter = ""
        self.assignee_filter = ""
        self.label_filter = ""
        self.priority_filter = ""
        self.key_filter = ""
        self.order_by = ""
        self.quick_filter_clauses: dict[str, str] = {}
        self.active_kind: ResourceKind = "issues"
        self.input_mode: Literal["find", "jql", "command", "transition", "assign", "edit_title", "comment", "none"] = "none"
        self.pending_issue_key = ""
        self.pending_transition_id = ""
        self.transition_choice_map: dict[str, str] = {}
        self.board_visible = False
        self.timeline_visible = False
        self.comment_feature = JiraCommentFeature(client)
        self.workflow_feature = JiraWorkflowFeature(client)
        self.command_suggester = CommandSuggester(
            lambda: self.all_issues,
            self._assignee_suggestion_names,
            self._command_verbs,
        )

    def _load_mention_users(self) -> list[dict]:
        """Load the complete assignable-user catalog once per TUI context."""
        if self._mention_users is None:
            try:
                self._mention_users = self.client.list_assignable_users(self.project_key, max_results=1000)
            except Exception:
                self._mention_users = []
            try:
                current_user = self.client.get_current_user()
            except Exception:
                current_user = {}
            current_id = current_user.get("accountId")
            if current_user and not any(
                user.get("accountId") == current_id
                or user.get("displayName") == current_user.get("displayName")
                for user in self._mention_users
            ):
                self._mention_users.append(current_user)
        return self._mention_users

    def _assignee_suggestion_names(self) -> list[str]:
        """Return display names from the complete cached user catalog."""
        return [
            str(user.get("displayName") or user.get("accountId") or "")
            for user in self._load_mention_users()
            if user.get("displayName") or user.get("accountId")
        ]

    def _status_order(self) -> list[str]:
        """Return status order configured by provider descriptor or default."""
        try:
            desc = self.client.describe()
            resource = desc.resource("issue") or desc.resource("issues")
            if resource:
                for f in resource.filters:
                    if f.name == "status" and f.special_values:
                        return list(f.special_values)
        except Exception:
            pass
        return DEFAULT_STATUS_ORDER

    def compose(self) -> ComposeResult:
        """Create the app layout."""
        yield JiraTopBar(self.current_user_display_name, title=f"Jira CLI — {self.context.label}")
        yield Label(f"[bold cyan]Jira CLI[/bold cyan] — Context: [bold yellow]{self.context.label}[/bold yellow]")
        yield Label("MODE: PROJECT", id="mode_context")
        yield Label(f"Source: project={self.project_key}", id="query_context")
        yield Input(placeholder="Find text in summary/description and press Enter", id="query_input")
        yield Input(placeholder="Filter issues (key/summary/status/assignee). Press Esc to clear", id="filter_input")
        with Horizontal(id="issue_actions_bar"):
            yield Label(id="issue_actions_hint")
        with Horizontal(id="issue_workspace"):
            with Vertical(id="issue_master"):
                yield IssueTableWidget(self.issues, id="issue_table")
                yield BoardWidget(self.issues, status_order=self._status_order(), id="issue_board")
                yield TimelineWidget(id="issue_timeline")
            yield IssueDetailWidget(id="issue_detail")
        yield UserTableWidget(self.users, id="user_table")
        yield VersionTableWidget(self.versions, id="version_table")
        yield LabelTableWidget(self.labels, id="label_table")
        yield UserDetailWidget(id="user_detail")
        yield VersionDetailWidget(id="version_detail")
        yield LabelDetailWidget(id="label_detail")
        yield Footer()

    def on_mount(self) -> None:
        """Initialize app widgets and the initial issue detail."""
        self.title = f"Jira CLI — {self.project_key}"
        query_input = self.query_one("#query_input", Input)
        filter_input = self.query_one("#filter_input", Input)
        query_input.display = False
        filter_input.display = False
        query_input.disabled = True
        filter_input.disabled = True
        table = self.query_one("#issue_table", IssueTableWidget)
        self.query_one("#issue_board", BoardWidget).display = False
        self.query_one("#issue_timeline", TimelineWidget).display = False
        self.query_one("#user_table", UserTableWidget).display = False
        self.query_one("#version_table", VersionTableWidget).display = False
        self.query_one("#label_table", LabelTableWidget).display = False
        self.query_one("#user_detail", UserDetailWidget).display = False
        self.query_one("#version_detail", VersionDetailWidget).display = False
        self.query_one("#label_detail", LabelDetailWidget).display = False
        table.focus()
        if self.issues:
            self.update_issue_detail(self.issues[0])
            self._prefetch_comments_for_issue(self.issues[0])
            self._children_prefetch.prefetch(self.issues[0])

    def _selected_issue(self) -> IssueRow | None:
        """Return the selected issue from the active table or board."""
        if self.active_kind != "issues":
            return None
        if self.board_visible:
            return self.query_one("#issue_board", BoardWidget).get_selected_issue()
        return self.query_one("#issue_table", IssueTableWidget).get_selected_issue()

    def _timeline_items(self) -> list[TimelineItem]:
        """Build timeline items from provider planning dates."""
        from datetime import date

        items = []
        for issue in self.issues:
            start = None
            if issue.start_date:
                try:
                    start = date.fromisoformat(issue.start_date[:10])
                except ValueError:
                    pass
            end = start
            if issue.due_date:
                try:
                    end = date.fromisoformat(issue.due_date[:10])
                except ValueError:
                    pass
            items.append(TimelineItem(issue.key, issue.summary, start, end, issue.status, issue.parent_key, issue.issue_type))
        return items

    def _timeline_markers(self) -> list[TimelineMarker]:
        """Build colored version markers from the active project's versions."""
        from datetime import date

        markers = []
        for version in self.versions:
            release_date = str(version.get("releaseDate") or "")[:10]
            if not release_date:
                continue
            try:
                marker_date = date.fromisoformat(release_date)
            except ValueError:
                continue
            color = "green" if version.get("released") else "cyan"
            if version.get("archived"):
                color = "dim"
            markers.append(TimelineMarker(str(version.get("name", "Version")), marker_date, color=color))
        return markers

    def action_toggle_timeline(self) -> None:
        """Toggle the prototype timeline view for the current issue set."""
        if self.active_kind != "issues":
            self._show_resource("issues")
        if not self.versions:
            try:
                self.versions = list_project_versions(self.client, self.project_key)
            except Exception:
                self.versions = []
        self.timeline_visible = not self.timeline_visible
        self.board_visible = False
        self.query_one("#issue_table", IssueTableWidget).display = not self.timeline_visible
        self.query_one("#issue_board", BoardWidget).display = False
        self.query_one("#issue_detail", IssueDetailWidget).display = False
        timeline = self.query_one("#issue_timeline", TimelineWidget)
        timeline.display = self.timeline_visible
        timeline.update_items(self._timeline_items())
        timeline.update_markers(self._timeline_markers())
        if self.timeline_visible:
            timeline.focus()
            self.notify("Timeline view")
        else:
            self.query_one("#issue_detail", IssueDetailWidget).display = True
            self.query_one("#issue_table", IssueTableWidget).focus()
            self.notify("Table view")
        self._update_issue_actions_bar()

    async def on_timeline_widget_issue_selected(self, event: TimelineWidget.IssueSelected) -> None:
        """Return from the timeline to the selected issue's normal action view."""
        await self._run_jql_context(f"key = {event.key}", f"Source: timeline -> {event.key}")
        self._show_resource("issues", board=False)
        self.notify(f"Issue {event.key}")

    async def action_clear_filter(self) -> None:
        """Clear active input and reset filter when needed."""
        query_input = self.query_one("#query_input", Input)
        if query_input.display:
            query_input.value = ""
            self._hide_query_input()
            self.input_mode = "none"
            self._update_query_context()
            return

        filter_input = self.query_one("#filter_input", Input)
        if filter_input.display:
            filter_input.value = ""
            self._hide_filter_input()
            await self._apply_filter("")
            self._update_query_context()
            return

        # No active input open: Esc acts as "back to project source".
        if self.query_mode != "project":
            await self.action_reset_source()

    async def action_reset_source(self) -> None:
        """Reset remote source context back to default project query."""
        self.query_mode = "project"
        self.query_expression = ""
        self.input_mode = "none"
        self.type_filter = self.status_filter = self.assignee_filter = self.label_filter = self.priority_filter = ""
        self.key_filter = self.order_by = ""
        self.quick_filter_clauses.clear()

        query_input = self.query_one("#query_input", Input)
        if query_input.display:
            query_input.value = ""
            self._hide_query_input()

        filter_input = self.query_one("#filter_input", Input)
        if filter_input.display:
            filter_input.value = ""
            self._hide_filter_input()

        await self.action_refresh()
        self.notify(f"Source reset to project={self.project_key}")

    def _supports_board(self) -> bool:
        """Check whether the active provider context supports board view."""
        try:
            desc = self.client.describe()
            return desc.supports_board
        except Exception:
            return True

    def action_toggle_board(self) -> None:
        """Toggle between table view and board (status columns) view."""
        if not self._supports_board():
            self.notify("Board view is not supported for single repository targets", severity="warning")
            return

        next_board_visible = not self.board_visible if self.active_kind == "issues" else True
        self._show_resource("issues", board=next_board_visible)

        if self.board_visible:
            self.query_one("#issue_board", BoardWidget).focus_board()
            self.notify("Board view (grouped by status)")
        else:
            self.notify("Table view")

    def _comment_prefetch_keys(self, issue: IssueRow) -> list[str]:
        """Return selected issue plus nearby visible issue keys for comment prefetch."""
        keys = [issue.key]
        visible_keys = [row.key for row in self.issues]
        if issue.key in visible_keys:
            index = visible_keys.index(issue.key)
            keys.extend(visible_keys[i] for i in range(index + 1, min(index + 4, len(visible_keys))))
        return list(dict.fromkeys(keys))

    def _prefetch_comments_for_issue(self, issue: IssueRow) -> None:
        """Prefetch selected and nearby issue comments without blocking navigation."""
        issue_key = issue.key
        keys = self._comment_prefetch_keys(issue)

        def load_comments() -> None:
            self.comment_feature.prefetch(keys)
            self.call_from_thread(self._refresh_issue_detail_if_selected, issue_key)

        self.run_worker(load_comments, group="comment-prefetch", exclusive=True, thread=True, exit_on_error=False)

    def _refresh_issue_detail_if_selected(self, issue_key: str) -> None:
        """Refresh cached comments only if the prefetched issue is still selected."""
        issue = self._selected_issue()
        if issue and issue.key == issue_key:
            self.update_issue_detail(issue)

    async def action_refresh(self) -> None:
        """Refresh the active resource list."""
        try:
            if self.active_kind == "users":
                self._show_assignable_users()
                return
            if self.active_kind == "versions":
                self._show_versions("Versions")
                return
            if self.active_kind == "labels":
                self._show_labels()
                return
            rows = self._run_remote_query()
            self.all_issues = rows
            self._update_query_context()
            filter_input = self.query_one("#filter_input", Input)
            await self._apply_filter(filter_input.value)
        except Exception as e:
            self.notify(f"Error refreshing: {escape(str(e))}", severity="error")

    def action_help(self) -> None:
        """Show help information."""
        help_text = (
            "[bold]Jira CLI TUI Shortcuts[/bold]\n\n"
            "[cyan]↑/↓[/cyan]      Navigate issues\n"
            "[cyan]p[/cyan]        Reset source to project\n"
            "[cyan]/[/cyan]        Focus live filter\n"
            "[cyan]f[/cyan]        Find by text (summary/description)\n"
            "[cyan]:[/cyan]        Command bar: table/board/view/actions|users/user=<q>/labels/versions|create/edit/related|type/status/assignee/label/priority=<value>|order=<field>|clear\n"
            "[cyan]b[/cyan]        Toggle board view (grouped by status)\n"
            "[cyan]v / o[/cyan]    View selected issue in web browser\n"
            "[cyan]Enter[/cyan]    Execute active query input\n"
            "[cyan]Esc[/cyan]      Close input or reset source\n"
            "[cyan]r[/cyan]        Refresh issues\n"
            "[cyan]q[/cyan]        Quit\n"
        )
        self.notify(help_text, title="Help")


def run_tui(
    client: IssueTrackerProvider,
    project_key: str,
    context: ProviderContext | None = None,
) -> None:
    """Launch the TUI application."""
    configure_tui_logging()
    query = JiraQuery(client)
    try:
        issues = query.search_project(project_key=project_key, max_results=100)
        current_user_display_name = ""
        try:
            current_user_display_name = client.get_current_user().get("displayName", "")
        except Exception:
            pass  # 'assignee=me' just won't resolve; not fatal for the rest of the TUI.
        app = JiraApp(client, project_key, issues, current_user_display_name, context=context)
        app.run()
    except Exception as e:
        print(f"Error launching TUI: {e}")
        raise

