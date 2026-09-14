"""Main Textual application for interactive Jira issue management."""

import webbrowser
from typing import Literal

from rich.markup import escape
from textual.app import ComposeResult, App
from textual.widgets import Label, DataTable, Footer, Input, ListView
from textual.binding import Binding

from jira_cli.models import IssueRow
from jira_cli.providers import IssueTrackerProvider, ProviderContext
from jira_cli.query import JiraQuery, order_by_clause
from jira_cli.quick_filters import QuickFilterResolver
from jira_cli.tui.features.board import BoardWidget
from jira_cli.tui.features.board.service import DEFAULT_STATUS_ORDER
from jira_cli.tui.features.comment import JiraCommentFeature
from jira_cli.tui.features.issues import IssueDetailWidget, IssueTableWidget
from jira_cli.tui.features.issues.modals import CommentModal, EditIssueModal
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
from jira_cli.tui.features.users import UserDetailWidget, UserTableWidget, list_project_users, search_project_users
from jira_cli.tui.features.versions import VersionDetailWidget, VersionTableWidget, list_project_versions
from jira_cli.tui.features.workflow import JiraWorkflowFeature
from jira_cli.tui.features.workflow.suggester import ActionSuggester
from jira_cli.tui.header import JiraTopBar

ResourceKind = Literal["issues", "users", "versions", "labels"]


class JiraApp(App):
    """Main Jira TUI Application."""

    BINDINGS = [
        Binding("q", "quit", "Quit", show=True),
        Binding("p", "reset_source", "Project", show=True),
        Binding("slash", "focus_filter", "Filter", show=True),
        Binding("f", "focus_find", "Find", show=True),
        Binding("j", "focus_jql", "Query", show=True),
        Binding("colon", "focus_command", "Command", show=True),
        Binding("b", "toggle_board", "Board", show=True),
        Binding("v", "open_issue", "Open in Browser", show=True),
        Binding("o", "open_issue", "Open in Browser", show=False),
        Binding("t", "transition", "Transition", show=True),
        Binding("a", "assign", "Assign", show=True),
        Binding("e", "edit_title", "Edit title", show=True),
        Binding("c", "comment", "Comment", show=True),
        Binding("n", "next_comment", "NextComment", show=True),
        Binding("left_square_bracket", "prev_comment", "PrevComment", show=False),
        Binding("right_square_bracket", "next_comment", "NextComment", show=False),
        Binding("u", "drill_up", "Parent", show=True),
        Binding("d", "drill_down", "Children", show=True),
        Binding("r", "refresh", "Refresh", show=True),
        Binding("question_mark", "help", "Help", show=True),
        Binding("escape", "clear_filter", "Clear Filter", show=False),
    ]

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
        height: 8;
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
        self.versions: list[dict] = []
        self.labels: list[dict] = []
        self.query_language = self.client.describe().query_language
        self.current_user_display_name = current_user_display_name
        self.query = JiraQuery(client)
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
        self.comment_feature = JiraCommentFeature(client)
        self.workflow_feature = JiraWorkflowFeature(client)
        self.command_suggester = CommandSuggester(lambda: self.all_issues)

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
        yield IssueTableWidget(self.issues, id="issue_table")
        yield BoardWidget(self.issues, status_order=self._status_order(), id="issue_board")
        yield UserTableWidget(self.users, id="user_table")
        yield VersionTableWidget(self.versions, id="version_table")
        yield LabelTableWidget(self.labels, id="label_table")
        yield IssueDetailWidget(id="issue_detail")
        yield UserDetailWidget(id="user_detail")
        yield VersionDetailWidget(id="version_detail")
        yield LabelDetailWidget(id="label_detail")
        yield Footer()

    def on_mount(self) -> None:
        """Initialize app on mount."""
        self.title = f"Jira CLI — {self.project_key}"
        query_input = self.query_one("#query_input", Input)
        filter_input = self.query_one("#filter_input", Input)
        query_input.display = False
        filter_input.display = False
        query_input.disabled = True
        filter_input.disabled = True
        table = self.query_one("#issue_table", IssueTableWidget)
        board = self.query_one("#issue_board", BoardWidget)
        board.display = False
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

    def _update_query_context(self) -> None:
        """Render active remote query context."""
        mode_text, source_text = build_query_labels(
            self.project_key, self.query_mode, self.query_expression, self.query_language
        )
        if self.active_kind != "issues":
            mode_text = f"MODE: {self.active_kind.upper()}"

        if self.type_filter:
            mode_text = f"{mode_text} | TYPE: {self.type_filter}"
        if self.status_filter:
            mode_text = f"{mode_text} | STATUS: {self.status_filter}"
        if self.assignee_filter:
            mode_text = f"{mode_text} | ASSIGNEE: {self.assignee_filter}"
        if self.label_filter:
            mode_text = f"{mode_text} | LABEL: {self.label_filter}"
        if self.priority_filter:
            mode_text = f"{mode_text} | PRIORITY: {self.priority_filter}"
        if self.key_filter:
            mode_text = f"{mode_text} | KEY: {self.key_filter}"
        if self.order_by:
            mode_text = f"{mode_text} | ORDER: {self.order_by}"

        mode_label = self.query_one("#mode_context", Label)
        mode_label.update(mode_text)

        context = self.query_one("#query_context", Label)
        context.update(source_text)

    def _run_remote_query(self) -> list[IssueRow]:
        """Run currently selected remote query source."""
        return run_remote_query(
            query=self.query,
            project_key=self.project_key,
            query_mode=self.query_mode,
            query_expression=self.query_expression,
            order_by=self.order_by,
            max_results=100,
        )

    def _selected_issue(self) -> IssueRow | None:
        """Return currently selected issue in the active view (table or board)."""
        if self.active_kind != "issues":
            return None
        if self.board_visible:
            board = self.query_one("#issue_board", BoardWidget)
            return board.get_selected_issue()
        table = self.query_one("#issue_table", IssueTableWidget)
        return table.get_selected_issue()

    def _show_resource(self, kind: ResourceKind, board: bool = False) -> None:
        """Switch the central content area between resource kinds and issue board mode."""
        self.active_kind = kind
        self.board_visible = kind == "issues" and board
        self.query_one("#issue_table", IssueTableWidget).display = kind == "issues" and not board
        self.query_one("#issue_board", BoardWidget).display = kind == "issues" and board
        self.query_one("#user_table", UserTableWidget).display = kind == "users"
        self.query_one("#version_table", VersionTableWidget).display = kind == "versions"
        self.query_one("#label_table", LabelTableWidget).display = kind == "labels"
        self.query_one("#issue_detail", IssueDetailWidget).display = kind == "issues"
        self.query_one("#user_detail", UserDetailWidget).display = kind == "users"
        self.query_one("#version_detail", VersionDetailWidget).display = kind == "versions"
        self.query_one("#label_detail", LabelDetailWidget).display = kind == "labels"

        if kind == "issues":
            if board:
                self.query_one("#issue_board", BoardWidget).focus_board()
            else:
                self.query_one("#issue_table", IssueTableWidget).focus()
        elif kind == "users":
            self.query_one("#user_table", UserTableWidget).focus()
        elif kind == "labels":
            self.query_one("#label_table", LabelTableWidget).focus()
        else:
            self.query_one("#version_table", VersionTableWidget).focus()
        self._update_query_context()

    def _restore_active_focus(self, preferred_key: str | None = None) -> None:
        """Return focus to the active main widget (table, board, users, labels, versions)."""
        if self.active_kind == "issues":
            if self.board_visible:
                board = self.query_one("#issue_board", BoardWidget)
                selected = self._selected_issue()
                key = preferred_key or (selected.key if selected else None)
                board.focus_board(preferred_key=key)
            else:
                self.query_one("#issue_table", IssueTableWidget).focus()
        elif self.active_kind == "users":
            self.query_one("#user_table", UserTableWidget).focus()
        elif self.active_kind == "labels":
            self.query_one("#label_table", LabelTableWidget).focus()
        elif self.active_kind == "versions":
            self.query_one("#version_table", VersionTableWidget).focus()

    def _show_query_input(self, placeholder: str, value: str = "") -> None:
        """Show query input consistently and focus it."""
        query_input = self.query_one("#query_input", Input)
        query_input.disabled = False
        query_input.placeholder = placeholder
        query_input.value = value
        query_input.display = True
        query_input.focus()

    def _hide_query_input(self) -> None:
        """Hide query input and return focus to active view."""
        query_input = self.query_one("#query_input", Input)
        query_input.display = False
        query_input.disabled = True
        self._restore_active_focus()

    def _show_filter_input(self) -> None:
        """Show filter input and focus it."""
        filter_input = self.query_one("#filter_input", Input)
        filter_input.disabled = False
        filter_input.display = True
        filter_input.focus()

    def _hide_filter_input(self) -> None:
        """Hide filter input and return focus to active view."""
        filter_input = self.query_one("#filter_input", Input)
        filter_input.display = False
        filter_input.disabled = True
        self._restore_active_focus()

    async def _run_jql_context(self, jql: str, context_label: str) -> None:
        """Execute JQL and set it as active remote context."""
        self.query_mode = "jql"
        self.query_expression = jql
        self.last_jql_expression = jql
        rows = self.query.search_custom_jql(jql, max_results=100)
        self.all_issues = rows
        self._show_resource("issues", board=self.board_visible)
        self._update_query_context()
        context = self.query_one("#query_context", Label)
        context.update(context_label)
        filter_input = self.query_one("#filter_input", Input)
        await self._apply_filter(filter_input.value)

    async def _render_issue_table(self, rows: list[IssueRow], preferred_key: str | None = None) -> None:
        """Render rows into table and board views, keeping selection if possible."""
        table = self.query_one("#issue_table", IssueTableWidget)
        table_selected = table.replace_rows(rows, preferred_key=preferred_key)

        board = self.query_one("#issue_board", BoardWidget)
        board_selected = await board.replace_rows(rows, preferred_key=preferred_key)

        selected_issue = board_selected if self.board_visible else table_selected
        if not selected_issue:
            detail = self.query_one("#issue_detail", IssueDetailWidget)
            detail.update_issue(None)
            return

        self.update_issue_detail(selected_issue)
        self._prefetch_comments_for_issue(selected_issue)

    async def _apply_filter(self, filter_text: str) -> None:
        """Apply the live '/' text filter to the currently loaded (already server-filtered) issues."""
        table = self.query_one("#issue_table", IssueTableWidget)
        current = table.get_selected_issue()
        preferred_key = current.key if current else None

        filtered = filter_issues(self.all_issues, filter_text)

        self.issues = filtered
        await self._render_issue_table(filtered, preferred_key=preferred_key)

    async def on_input_changed(self, event: Input.Changed) -> None:
        """Incrementally filter table rows when filter input changes."""
        if event.input.id != "filter_input":
            return
        await self._apply_filter(event.value)

    async def _apply_loaded_rows(self, rows: list[IssueRow], success_message: str) -> None:
        """Update issue store and refresh table/detail with current local filter."""
        self.all_issues = rows
        self._show_resource("issues", board=self.board_visible)
        self._update_query_context()
        filter_input = self.query_one("#filter_input", Input)
        await self._apply_filter(filter_input.value)
        self.notify(success_message)

    async def _submit_find(self, expression: str) -> None:
        """Handle submitted input in find mode."""
        self.query_mode = "find"
        self.query_expression = expression
        self.last_find_expression = expression
        rows = self._run_remote_query()
        await self._apply_loaded_rows(rows, f"Loaded {len(rows)} issues")
    async def _submit_jql(self, expression: str) -> None:
        """Handle submitted input in jql mode."""
        self.query_mode = "jql"
        self.query_expression = expression
        self.last_jql_expression = expression
        rows = self._run_remote_query()
        await self._apply_loaded_rows(rows, f"Loaded {len(rows)} issues")

    async def _submit_transition(self, expression: str) -> None:
        """Handle submitted transition command asynchronously in background thread to avoid UI lag."""
        issue_key = self.pending_issue_key
        transition_id = self.pending_transition_id
        choice_map = self.transition_choice_map
        self.pending_transition_id = ""

        def run_transition() -> tuple[str, list[IssueRow]]:
            message = self.workflow_feature.submit_transition_expression(
                issue_key,
                expression,
                choice_map,
                default_transition_id=transition_id,
            )
            rows = self._run_remote_query()
            return message, rows

        async def on_done(worker) -> None:
            if worker.result:
                message, rows = worker.result
                self.all_issues = rows
                self.notify(message)
                filter_input = self.query_one("#filter_input", Input)
                await self._apply_filter(filter_input.value)
                self._restore_active_focus(preferred_key=issue_key)

        self.run_worker(run_transition, thread=True, exclusive=True, exit_on_error=False)

    async def _submit_assign(self, expression: str) -> None:
        """Handle submitted assign command asynchronously in background thread."""
        issue_key = self.pending_issue_key

        def run_assign() -> tuple[str, list[IssueRow]]:
            message = self.workflow_feature.submit_assign_expression(issue_key, expression)
            rows = self._run_remote_query()
            return message, rows

        async def on_done(worker) -> None:
            if worker.result:
                message, rows = worker.result
                self.all_issues = rows
                self.notify(message)
                filter_input = self.query_one("#filter_input", Input)
                await self._apply_filter(filter_input.value)
                self._restore_active_focus(preferred_key=issue_key)

        self.run_worker(run_assign, thread=True, exclusive=True, exit_on_error=False)

    async def _submit_edit_title(self, expression: str) -> None:
        """Update the selected issue title through the active provider."""
        title = expression.strip()
        if not title:
            self.notify("Title is empty", severity="warning")
            return
        issue_key = self.pending_issue_key
        self.client.update_issue(issue_key, {"summary": title})
        self.notify(f"Updated title for {issue_key}")
        await self.action_refresh()

    async def _submit_edit_fields(self, fields: dict) -> None:
        """Apply fields returned by the issue edit modal."""
        if not fields.get("summary"):
            self.notify("Title is empty", severity="warning")
            return
        self.client.update_issue(self.pending_issue_key, fields)
        self.notify(f"Updated {self.pending_issue_key}")
        await self.action_refresh()

    async def _submit_comment(self, expression: str) -> None:
        """Handle submitted comment input."""
        try:
            message = self.comment_feature.submit_comment_expression(self.pending_issue_key, expression)
        except ValueError as value_error:
            self.notify(str(value_error), severity="error")
            return

        self.notify(message)
        self.comment_feature.invalidate_issue(self.pending_issue_key)
        await self.action_refresh()

    async def _submit_by_mode(self, expression: str) -> None:
        """Dispatch query input submission to active input mode handler."""
        if self.input_mode == "find":
            await self._submit_find(expression)
            return
        if self.input_mode == "jql":
            await self._submit_jql(expression)
            return
        if self.input_mode == "command":
            await self._submit_command(expression)
            return
        if self.input_mode == "transition":
            await self._submit_transition(expression)
            return
        if self.input_mode == "assign":
            await self._submit_assign(expression)
            return
        if self.input_mode == "edit_title":
            await self._submit_edit_title(expression)
            return
        if self.input_mode == "comment":
            await self._submit_comment(expression)
            return

        self.notify("No active input mode", severity="warning")

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Run remote query when query input is submitted."""
        if event.input.id != "query_input":
            return

        expression = event.value.strip()
        if not expression:
            self.notify("Query text is empty", severity="warning")
            return

        selected = self._selected_issue()
        preferred_key = selected.key if selected else None

        self._hide_query_input()

        try:
            await self._submit_by_mode(expression)
            self.input_mode = "none"
        except Exception as e:
            self.notify(f"Query failed: {escape(str(e))}", severity="error")
        finally:
            self._restore_active_focus(preferred_key=preferred_key)

    def action_focus_filter(self) -> None:
        """Show and focus filter input."""
        self._show_filter_input()

    def action_focus_command(self) -> None:
        """Show and focus the ':' command bar (k9s/sofka-style: views + quick filters)."""
        self.input_mode = "command"
        mode_label = self.query_one("#mode_context", Label)
        mode_label.update("MODE: COMMAND (INPUT)")
        query_input = self.query_one("#query_input", Input)
        query_input.suggester = self.command_suggester
        self._show_query_input(
            "issues/table/board | users/user=<q>/labels/versions | type/status/assignee/label/priority=<value> | order=<field> | overdue[=me] | clear"
        )

    async def _submit_command(self, expression: str) -> None:
        """Parse and apply a ':' command: view switch, quick filter, or clear."""
        verb, arg = parse_command(expression)

        if verb in ("table", "issues"):
            self._show_resource("issues", board=False)
            return
        if verb in ("board", "b"):
            self._show_resource("issues", board=True)
            return
        if verb in ("v", "view", "open"):
            self.action_open_issue()
            return
        if verb == "next":
            issue = self._selected_issue()
            try:
                context = self.workflow_feature.prepare_next_transition_action(issue, self._status_order())
            except ValueError as value_error:
                self.notify(str(value_error), severity="warning")
                return
            self.pending_issue_key = context.issue_key
            self.pending_transition_id = context.default_transition_id
            self.input_mode = context.input_mode
            self.query_one("#mode_context", Label).update(context.mode_label)
            self.transition_choice_map = context.choice_map
            self.notify(context.notice, timeout=8)
            self._show_query_input(context.placeholder)
            return
        if verb == "clear":
            self.type_filter = self.status_filter = self.assignee_filter = self.label_filter = self.priority_filter = ""
            self.key_filter = self.order_by = ""
            self.quick_filter_clauses.clear()
            await self._run_combined_quick_filters("Quick filters cleared")
            return
        if verb == "me":
            self._show_current_user()
            return
        if verb == "users":
            self._show_assignable_users()
            return
        if verb == "labels":
            self._show_labels()
            return
        if verb == "user":
            if not arg:
                self.notify("Usage: user=<query>", severity="warning")
                return
            self._show_user_search(arg)
            return
        if verb in {"versions", "milestones"}:
            self._show_versions("Milestones" if verb == "milestones" else "Versions")
            return
        if verb == "order":
            if not arg:
                self.notify("Usage: order=<field> [asc|desc]", severity="warning")
                return
            if arg.strip().lower() == "clear":
                self.order_by = ""
                await self._run_combined_quick_filters("Order cleared")
                return
            order_by_clause(arg)
            self.order_by = arg
            await self._run_combined_quick_filters(f"Order={arg}")
            return
        if verb == "overdue":
            mine = arg.strip().lower() == "me"
            label = "overdue" + (" (mine)" if mine else "")
            await self._run_jql_context(JiraQuery.overdue_jql(self.project_key, mine=mine), f"Source: {label}")
            return

        if verb in QUICK_FILTER_DIMENSIONS:
            if not arg:
                self.notify(f"Usage: {verb}=<value>", severity="warning")
                return
            await self._apply_quick_filter(verb, arg)
            return

        resolved = resolve_bare_quick_filter(self.all_issues, expression)
        if resolved:
            dimension, match = resolved
            await self._apply_quick_filter(dimension, match)
            return

        self.notify(f"Unknown command: {expression}", severity="warning")

    async def _apply_quick_filter(self, dimension: str, value: str) -> None:
        """Resolve one quick-filter dimension and run it server-side (JQL) — never local-only,
        so it isn't limited to whatever page of issues happens to already be loaded."""
        distinct_fn, attr = QUICK_FILTER_DIMENSIONS[dimension]
        known_values = distinct_fn(self.all_issues)
        display_value, clause = self.quick_filter_resolver.resolve(dimension, value, known_values)
        if not display_value:
            self.notify(f"Usage: {dimension}=<value>", severity="warning")
            return

        setattr(self, attr, display_value)
        self.quick_filter_clauses[dimension] = clause
        await self._run_combined_quick_filters(f"{dimension.capitalize()}={display_value}")

    async def _run_combined_quick_filters(self, message: str) -> None:
        """Rebuild JQL from all active quick filters and fetch matching issues from Jira."""
        clauses = " AND ".join(self.quick_filter_clauses.values())
        jql = f"project = {self.project_key}" + (f" AND {clauses}" if clauses else "")
        order_clause = order_by_clause(self.order_by)
        if order_clause:
            jql = f"{jql} {order_clause}"
        await self._run_jql_context(jql, f"Source: {self.query_language.lower()} {jql}")
        self.notify(message)

    def _show_current_user(self) -> None:
        """Show authenticated user as the active user resource view."""
        self._replace_users([self.client.get_current_user()], "Source: current user")

    def _show_assignable_users(self) -> None:
        """Show project assignable users as the active user resource view."""
        self._replace_users(list_project_users(self.client, self.project_key), f"Source: users in {self.project_key}")

    def _show_user_search(self, query: str) -> None:
        """Search users as the active user resource view."""
        users = search_project_users(self.client, self.project_key, query)
        self._replace_users(users, f"Source: users matching '{query}'")

    def _show_versions(self, title: str) -> None:
        """Show project fix versions/milestones as the active version resource view."""
        self._replace_versions(list_project_versions(self.client, self.project_key), f"Source: {title.lower()} in {self.project_key}")

    def _show_labels(self) -> None:
        """Show project/repository labels as the active label resource view."""
        self._replace_labels(list_project_labels(self.client, self.project_key), f"Source: labels in {self.project_key}")

    def _replace_users(self, users: list[dict], source_label: str) -> None:
        """Replace user rows and switch to the users resource view."""
        self.users = users
        table = self.query_one("#user_table", UserTableWidget)
        selected = table.replace_rows(users)
        self.query_one("#user_detail", UserDetailWidget).update_user(selected)
        self._show_resource("users")
        self.query_one("#query_context", Label).update(source_label)

    def _replace_versions(self, versions: list[dict], source_label: str) -> None:
        """Replace version rows and switch to the versions resource view."""
        self.versions = versions
        table = self.query_one("#version_table", VersionTableWidget)
        selected = table.replace_rows(versions)
        self.query_one("#version_detail", VersionDetailWidget).update_version(selected)
        self._show_resource("versions")
        self.query_one("#query_context", Label).update(source_label)

    def _replace_labels(self, labels: list[dict], source_label: str) -> None:
        """Replace label rows and switch to the labels resource view."""
        self.labels = labels
        table = self.query_one("#label_table", LabelTableWidget)
        selected = table.replace_rows(labels)
        self.query_one("#label_detail", LabelDetailWidget).update_label(selected)
        self._show_resource("labels")
        self.query_one("#query_context", Label).update(source_label)

    def action_focus_find(self) -> None:
        """Show and focus find query input."""
        self.input_mode = "find"
        mode_label = self.query_one("#mode_context", Label)
        mode_label.update("MODE: FIND (INPUT)")
        query_input = self.query_one("#query_input", Input)
        query_input.suggester = None
        self._show_query_input("Find text in summary/description and press Enter", self.last_find_expression)

    def action_focus_jql(self) -> None:
        """Show and focus provider query input."""
        self.input_mode = "jql"
        mode_label = self.query_one("#mode_context", Label)
        mode_label.update(f"MODE: {self.query_language.upper()} (INPUT)")
        query_input = self.query_one("#query_input", Input)
        query_input.suggester = None
        self._show_query_input(self._provider_query_placeholder(), self.last_jql_expression)

    def _provider_query_placeholder(self) -> str:
        """Return a provider-specific example for the free query input."""
        if self.context.provider == "github":
            return 'GitHub issue query, e.g. status = "all" AND labels = "bug" ORDER BY updated DESC'
        if self.context.provider == "demo":
            return 'Demo query, e.g. priority = "Highest" ORDER BY updated DESC'
        return f'JQL, e.g. project = {self.project_key} AND status = "In Progress" ORDER BY updated DESC'

    def action_transition(self) -> None:
        """Prompt for transition ID or name and execute transition with autocomplete."""
        issue = self._selected_issue()
        try:
            context = self.workflow_feature.prepare_transition_action(issue)
        except ValueError as value_error:
            self.notify(str(value_error), severity="warning")
            return
        except Exception as e:
            self.notify(f"Cannot load transitions: {e}", severity="error")
            return

        self.pending_issue_key = context.issue_key
        self.pending_transition_id = context.default_transition_id
        self.input_mode = context.input_mode
        mode_label = self.query_one("#mode_context", Label)
        mode_label.update(context.mode_label)
        self.transition_choice_map = context.choice_map

        # Collect transition name / ID candidates for autocomplete
        candidates = []
        for key in context.choice_map.keys():
            if not key.islower() or key in context.choice_map.values():
                candidates.append(key)
        candidates = list(dict.fromkeys(candidates))

        query_input = self.query_one("#query_input", Input)
        query_input.suggester = ActionSuggester(candidates)

        self.notify(context.notice, timeout=8)
        self._show_query_input("Transition status name or ID [| optional comment]")

    def action_assign(self) -> None:
        """Prompt for assignee and execute assignment with autocomplete."""
        issue = self._selected_issue()
        try:
            context = self.workflow_feature.prepare_assign_action(issue)
        except ValueError as value_error:
            self.notify(str(value_error), severity="warning")
            return

        self.pending_issue_key = context.issue_key
        self.input_mode = context.input_mode
        mode_label = self.query_one("#mode_context", Label)
        mode_label.update(context.mode_label)

        try:
            assignable = self.client.list_assignable_users(self.project_key, max_results=20)
        except Exception:
            assignable = []

        candidates = []
        user_labels = []
        for u in assignable:
            name = u.get("displayName") or ""
            acct = u.get("accountId") or ""
            if name and acct and name != acct:
                user_labels.append(f"{name} (@{acct})")
                candidates.extend([name, acct, f"@{acct}"])
            else:
                entry = name or acct
                if entry:
                    user_labels.append(entry)
                    candidates.extend([entry, f"@{entry}"] if not entry.startswith("@") else [entry])

        candidates = list(dict.fromkeys(candidates))
        query_input = self.query_one("#query_input", Input)
        query_input.suggester = ActionSuggester(candidates)

        notice_text = "Assignees: " + " | ".join(user_labels[:5]) if user_labels else "Assignee: type user name or handle"
        self.notify(notice_text, timeout=8)
        self._show_query_input("Assignee name or @handle (press Tab for completion)")

    def action_edit_title(self) -> None:
        """Open the common issue edit form."""
        issue = self._selected_issue()
        if not issue:
            self.notify("No issue selected", severity="warning")
            return

        self.pending_issue_key = issue.key
        self.push_screen(
            EditIssueModal(issue.key, issue.summary, labels=issue.labels),
            lambda fields: self.run_worker(self._submit_edit_fields(fields), exclusive=True) if fields else None,
        )

    def action_comment(self) -> None:
        """Open the comment thread and multiline composer."""
        issue = self._selected_issue()
        try:
            context = self.comment_feature.prepare_comment_action(issue)
        except ValueError as value_error:
            self.notify(str(value_error), severity="warning")
            return

        self.pending_issue_key = context.issue_key
        self.push_screen(
            CommentModal(issue.key, self.comment_feature.thread_view(issue.key)),
            lambda text: self.run_worker(self._submit_comment(text), exclusive=True) if text else None,
        )

    def action_next_comment(self) -> None:
        """Select next comment for the selected issue."""
        issue = self._selected_issue()
        if not issue:
            self.notify("No issue selected", severity="warning")
            return
        moved = self.comment_feature.next_comment(issue.key)
        if not moved:
            self.notify("No comments on this issue", severity="warning")
            return
        self.update_issue_detail(issue)

    def action_prev_comment(self) -> None:
        """Select previous comment for the selected issue."""
        issue = self._selected_issue()
        if not issue:
            self.notify("No issue selected", severity="warning")
            return
        moved = self.comment_feature.prev_comment(issue.key)
        if not moved:
            self.notify("No comments on this issue", severity="warning")
            return
        self.update_issue_detail(issue)

    async def action_drill_up(self) -> None:
        """Drill up to parent issue."""
        issue = self._selected_issue()
        if not issue:
            self.notify("No issue selected", severity="warning")
            return
        if not issue.parent_key:
            self.notify(f"{issue.key} has no parent", severity="warning")
            return
        try:
            await self._run_jql_context(
                f"key = {issue.parent_key}", f"Source: parent of {issue.key} -> {issue.parent_key}"
            )
        except Exception as e:
            self.notify(f"Drill up failed: {e}", severity="error")

    async def action_drill_down(self) -> None:
        """Drill down into child issues.

        Uses locally known subtasks if any (fast); otherwise queries Jira for issues whose
        'parent' is this one — the field modern Jira Cloud hierarchy uses for Epic -> Story/Task
        (and Story -> Sub-task) children, which aren't exposed via the issue's own 'subtasks'.
        """
        issue = self._selected_issue()
        if not issue:
            self.notify("No issue selected", severity="warning")
            return
        try:
            if issue.child_keys:
                keys = ",".join(issue.child_keys)
                await self._run_jql_context(
                    f"key in ({keys}) ORDER BY key",
                    f"Source: children of {issue.key} ({len(issue.child_keys)})",
                )
                return

            await self._run_jql_context(JiraQuery.children_jql(issue.key), f"Source: children of {issue.key}")
            if not self.all_issues:
                self.notify(f"{issue.key} has no child issues", severity="warning")
        except Exception as e:
            self.notify(f"Drill down failed: {e}", severity="error")

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

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """Update details when row highlight changes in the issue table."""
        if event.data_table.id == "user_table":
            user = self.query_one("#user_table", UserTableWidget).get_selected_user()
            self.query_one("#user_detail", UserDetailWidget).update_user(user)
            return
        if event.data_table.id == "version_table":
            version = self.query_one("#version_table", VersionTableWidget).get_selected_version()
            self.query_one("#version_detail", VersionDetailWidget).update_version(version)
            return
        if event.data_table.id == "label_table":
            label = self.query_one("#label_table", LabelTableWidget).get_selected_label()
            self.query_one("#label_detail", LabelDetailWidget).update_label(label)
            return
        if event.data_table.id != "issue_table":
            return
        table = self.query_one("#issue_table", IssueTableWidget)
        selected = table.get_selected_issue()
        if selected:
            self.update_issue_detail(selected)
            self._prefetch_comments_for_issue(selected)

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        """Update details when a board card is highlighted."""
        if not self.board_visible or event.item is None:
            return
        issue = getattr(event.item, "issue", None)
        if issue:
            self.update_issue_detail(issue)
            self._prefetch_comments_for_issue(issue)

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

    def update_issue_detail(self, issue: IssueRow) -> None:
        """Update the detail view with selected issue."""
        comment_text, comment_position = self.comment_feature.cached_view(issue.key)
        detail = self.query_one("#issue_detail", IssueDetailWidget)
        detail.update_issue(issue, comment_text=comment_text, comment_position=comment_position)

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

    def action_open_issue(self) -> None:
        """Open selected issue in browser from either list view or board view."""
        if self.context.provider == "demo":
            self.notify("Browser opening disabled in demo mode", severity="warning")
            return
        issue = self._selected_issue()
        if issue:
            try:
                if hasattr(self.client, "get_issue_url"):
                    url = self.client.get_issue_url(issue.key)
                else:
                    url = f"{self.client.base_url.rstrip('/')}/browse/{issue.key}"
                webbrowser.open(url)
                self.notify(f"Opened {issue.key} in browser")
            except Exception as e:
                self.notify(f"Error: {e}", severity="error")
        else:
            self.notify("No issue selected", severity="warning")

    def action_help(self) -> None:
        """Show help information."""
        help_text = (
            "[bold]Jira CLI TUI Shortcuts[/bold]\n\n"
            "[cyan]↑/↓[/cyan]      Navigate issues\n"
            "[cyan]p[/cyan]        Reset source to project\n"
            "[cyan]/[/cyan]        Focus live filter\n"
            "[cyan]f[/cyan]        Find by text (summary/description)\n"
            f"[cyan]j[/cyan]        Run {self.query_language} query\n"
            "[cyan]:[/cyan]        Command bar: issues/table/board/view|next|users/user=<q>/labels/versions|type/status/assignee/label/priority=<value>|order=<field>|overdue[=me]|clear\n"
            "[cyan]b[/cyan]        Toggle board view (grouped by status)\n"
            "[cyan]v / o[/cyan]    Open selected issue in browser\n"
            "[cyan]Enter[/cyan]    Execute active query input\n"
            "[cyan]t[/cyan]        Transition selected issue\n"
            "[cyan]a[/cyan]        Assign selected issue\n"
            "[cyan]c[/cyan]        Add comment (plain/md/adf)\n"
            "[cyan]n / ][/cyan]    Next comment\n"
            "[cyan][[/cyan]        Previous comment\n"
            "[cyan]u[/cyan]        Drill up to parent issue\n"
            "[cyan]d[/cyan]        Drill down to child issues\n"
            "[cyan]Esc[/cyan]      Close input or reset source\n"
            "[cyan]r[/cyan]        Refresh issues\n"
            "[cyan]q[/cyan]        Quit\n"
        )
        self.notify(help_text, title="Help")


def run_tui(client: IssueTrackerProvider, project_key: str, context: ProviderContext | None = None) -> None:
    """Launch the TUI application."""
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

