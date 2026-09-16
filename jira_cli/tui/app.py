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
from jira_cli.quick_filters import QuickFilterResolver, normalize_for_match
from jira_cli.tui.features.board import BoardWidget
from jira_cli.tui.features.board.service import DEFAULT_STATUS_ORDER
from jira_cli.tui.features.comment import JiraCommentFeature
from jira_cli.tui.features.issues import IssueDetailWidget, IssueTableWidget
from jira_cli.tui.features.issues.modals import CommentModal, EditIssueModal, IssueActionsModal
from jira_cli.tui.features.labels import LabelDetailWidget, LabelTableWidget, list_project_labels
from jira_cli.tui.features.labels.modals import LabelModal
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
from jira_cli.tui.features.versions.modals import VersionModal
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
        Binding("colon", "focus_command", "Command", show=True),
        Binding("n", "create_resource", "New", show=True),
        Binding("ctrl+t", "toggle_theme", "Theme", show=True),
        Binding("b", "toggle_board", "Board", show=True),
        Binding("v", "open_issue", "View in Web", show=True),
        Binding("o", "open_issue", "Open in Browser", show=False),
        Binding("insert", "create_resource", "New", show=False),
        Binding("delete", "delete_resource", "Delete", show=True),
        Binding("i", "issues_for_resource", "Issues", show=True),
        Binding("x", "issue_actions", "Actions", show=True),
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
            height: 12;
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
        self.refresh_bindings()

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        """Expose only actions that make sense for the active resource and provider."""
        issue_actions = {
            "focus_find", "toggle_board", "open_issue", "issue_actions",
            "transition", "assign", "comment", "drill_up", "drill_down",
        }
        if action in issue_actions:
            return self.active_kind == "issues"
        if action == "edit_resource":
            if self.active_kind == "issues":
                return True
            return self.active_kind in {"labels", "versions"} and self._resource_supports_action(
                self.active_kind, "edit"
            )
        if action == "create_resource":
            return self.active_kind in {"issues", "labels", "versions"} and self._resource_supports_action(
                self.active_kind, "create"
            )
        if action == "delete_resource":
            return self.active_kind in {"labels", "versions"} and self._resource_supports_action(
                self.active_kind, "delete"
            )
        if action == "issues_for_resource":
            return self.active_kind in {"labels", "versions", "users"}
        return True

    def _resource_supports_action(self, kind: str, action: str) -> bool:
        resource = self.client.describe().resource(kind)
        return bool(resource and any(item.name == action for item in resource.actions))

    def _command_verbs(self) -> list[str]:
        """Return command-palette verbs available in the current resource context."""
        verbs = ["users", "labels", "versions", "clear"]
        if self.active_kind == "issues":
            verbs.extend([
                "table", "board", "view", "actions", "create", "order=",
                *(f"{verb}=" for verb in QUICK_FILTER_DIMENSIONS),
            ])
        elif self.active_kind == "users":
            verbs.append("user=")
        elif self.active_kind in {"labels", "versions"}:
            verbs.extend(["edit", "related"])
        for action in ("create", "edit", "delete"):
            action_name = f"{action}_resource" if action != "edit" else "edit_resource"
            if self.check_action(action_name, ()):
                if action not in verbs:
                    verbs.append(action)
        return verbs

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
        placeholders = {
            "issues": "Filter issues (key/summary/status/assignee)",
            "users": "Filter users by name/email; use 'me' for current user",
            "versions": "Filter versions/milestones by name/status/date",
            "labels": "Filter labels by name/description",
        }
        filter_input.placeholder = placeholders[self.active_kind]
        filter_input.disabled = False
        filter_input.display = True
        filter_input.focus()

    def _hide_filter_input(self) -> None:
        """Hide filter input and return focus to active view."""
        filter_input = self.query_one("#filter_input", Input)
        filter_input.display = False
        filter_input.disabled = True
        filter_input.value = ""
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
        """Apply the live '/' filter to the active resource view."""
        if self.active_kind == "users":
            query = normalize_for_match(filter_text)
            if query == "me":
                query = normalize_for_match(self.current_user_display_name)
            users = [
                user
                for user in self.users
                if not query
                or query in normalize_for_match(str(user.get("displayName", "")))
                or query in normalize_for_match(str(user.get("emailAddress", "")))
                or query in normalize_for_match(str(user.get("accountId", "")))
            ]
            selected = self.query_one("#user_table", UserTableWidget).replace_rows(users)
            self.query_one("#user_detail", UserDetailWidget).update_user(selected)
            return
        if self.active_kind == "versions":
            query = normalize_for_match(filter_text)
            versions = [
                version
                for version in self.versions
                if not query
                or query in normalize_for_match(str(version.get("name", "")))
                or query in normalize_for_match("released" if version.get("released") else "unreleased")
                or query in normalize_for_match(str(version.get("releaseDate", "")))
            ]
            selected = self.query_one("#version_table", VersionTableWidget).replace_rows(versions)
            self.query_one("#version_detail", VersionDetailWidget).update_version(selected)
            return
        if self.active_kind == "labels":
            query = normalize_for_match(filter_text)
            labels = [
                label
                for label in self.labels
                if not query
                or query in normalize_for_match(str(label.get("name", "")))
                or query in normalize_for_match(str(label.get("description", "")))
            ]
            selected = self.query_one("#label_table", LabelTableWidget).replace_rows(labels)
            self.query_one("#label_detail", LabelDetailWidget).update_label(selected)
            return

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
        update_fields = {key: value for key, value in fields.items() if key != "action"}
        self.client.update_issue(self.pending_issue_key, update_fields)
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
        self._show_query_input("table/board/users/labels/versions | actions/create/edit/related | status= | assignee= | label= | clear")

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
        if verb in ("actions", "action", "x"):
            self.action_issue_actions()
            return
        if verb == "create":
            if not self.check_action("create_resource", ()):
                self.notify("Create is not available in this context", severity="warning")
                return
            self.action_create_resource()
            return
        if verb == "edit":
            if not self.check_action("edit_resource", ()):
                self.notify("Edit is not available in this context", severity="warning")
                return
            self.action_edit_resource()
            return
        if verb == "delete":
            if not self.check_action("delete_resource", ()):
                self.notify("Delete is not available in this context", severity="warning")
                return
            self.action_delete_resource()
            return
        if verb == "related":
            await self.action_issues_for_resource()
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
        users = sorted(
            self._load_mention_users(),
            key=lambda user: normalize_for_match(str(user.get("displayName") or user.get("accountId") or "")),
        )
        self._replace_users(users, f"Source: users in {self.project_key}")

    def action_toggle_theme(self) -> None:
        """Toggle between Textual's default dark and light themes."""
        self.theme = "textual-light" if self.theme == "textual-dark" else "textual-dark"
        self.notify(f"Theme: {self.theme}")

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
        self._labels_loaded = True

    def _label_names(self) -> list[str]:
        """Return the cached label catalog, loading it once on demand."""
        if not self._labels_loaded:
            self.labels = list_project_labels(self.client, self.project_key)
            self._labels_loaded = True
        return [str(label.get("name", "")) for label in self.labels if label.get("name")]

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

        candidates = ["me"]
        user_labels = ["me (current user)"]
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

    def action_edit_resource(self) -> None:
        """Edit the selected item in the active resource view."""
        if self.active_kind == "labels":
            self._edit_selected_label()
            return
        if self.active_kind == "versions":
            self._edit_selected_version()
            return
        self.action_edit_title()

    def action_edit_title(self) -> None:
        """Open the common issue edit form."""
        issue = self._selected_issue()
        if not issue:
            self.notify("No issue selected", severity="warning")
            return

        self.pending_issue_key = issue.key
        self.push_screen(
            EditIssueModal(
                issue.key,
                issue.summary,
                description=issue.description,
                labels=issue.labels,
                label_candidates=self._label_names(),
            ),
            lambda fields: self.run_worker(self._submit_edit_fields(fields), exclusive=True) if fields else None,
        )

    def action_create_resource(self) -> None:
        """Open a create modal for the active resource."""
        if self.active_kind == "issues":
            repositories = self.client.list_issue_repositories() if hasattr(self.client, "list_issue_repositories") else []
            if self.context.provider == "github" and self.client.describe().supports_board and not repositories:
                self.notify("No repository is available for issue creation in this project", severity="warning")
                return
            self.push_screen(
                EditIssueModal(label_candidates=self._label_names(), repository_candidates=repositories),
                self._handle_new_issue_result,
            )
        elif self.active_kind == "labels":
            self.push_screen(LabelModal(), self._handle_label_result)
        elif self.active_kind == "versions":
            self.push_screen(VersionModal(), self._handle_version_result)

    def _handle_new_issue_result(self, result: dict | None) -> None:
        """Create a new issue from the common issue modal."""
        if not result or not result.get("summary"):
            return
        try:
            created = self.client.create_issue(
                self.project_key,
                result["summary"],
                body=result.get("description") or None,
                labels=result.get("labels") or None,
                repository=result.get("repository") or None,
            )
            key = created.get("key", "issue")
            self.notify(f"Created {key}")
            self.run_worker(self.action_refresh(), exclusive=True)
        except Exception as exc:
            self.notify(f"Issue creation failed: {escape(str(exc))}", severity="error")

    def action_delete_resource(self) -> None:
        """Open the selected resource in delete-ready edit mode."""
        if self.active_kind == "labels":
            self._edit_selected_label()
        elif self.active_kind == "versions":
            self._edit_selected_version()

    def _edit_selected_label(self) -> None:
        label = self.query_one("#label_table", LabelTableWidget).get_selected_label()
        if not label:
            self.notify("No label selected", severity="warning")
            return
        resource = self.client.describe().resource("labels")
        supports_metadata = bool(resource and "color" in resource.fields)
        self.push_screen(
            LabelModal(label, supports_metadata=supports_metadata, bulk=self.context.provider == "jira"),
            self._handle_label_result,
        )

    def _handle_label_result(self, result: dict | None) -> None:
        if not result:
            return
        try:
            if result["action"] == "create":
                self.client.create_label(
                    self.project_key, result["name"], result["color"], result["description"]
                )
            elif result["action"] == "edit":
                self.client.update_label(
                    self.project_key,
                    result["original_name"],
                    result["name"],
                    result["color"],
                    result["description"],
                )
            elif result["action"] == "delete":
                self.client.delete_label(self.project_key, result["name"])
            self._labels_loaded = False
            self._show_labels()
            self.notify("Labels updated")
        except Exception as exc:
            self.notify(f"Label update failed: {escape(str(exc))}", severity="error")

    def _edit_selected_version(self) -> None:
        version = self.query_one("#version_table", VersionTableWidget).get_selected_version()
        if not version:
            self.notify("No version selected", severity="warning")
            return
        self.push_screen(VersionModal(version), self._handle_version_result)

    def _handle_version_result(self, result: dict | None) -> None:
        if not result:
            return
        try:
            if result["action"] == "create":
                self.client.create_version(
                    self.project_key,
                    result["name"],
                    description=result["description"],
                    release_date=result["releaseDate"] or None,
                )
                if result["released"]:
                    self.client.update_version(self.project_key, result["name"], released=True)
            elif result["action"] == "edit":
                self.client.update_version(
                    self.project_key,
                    result["original_name"],
                    name=result["name"],
                    description=result["description"],
                    release_date=result["releaseDate"],
                    released=result["released"],
                )
            elif result["action"] == "delete":
                self.client.delete_version(self.project_key, result["name"])
            self._show_versions("Versions")
            self.notify("Versions updated")
        except Exception as exc:
            self.notify(f"Version update failed: {escape(str(exc))}", severity="error")

    async def action_issues_for_resource(self) -> None:
        """Show issues related to the selected label, version, or user."""
        if self.active_kind == "labels":
            label = self.query_one("#label_table", LabelTableWidget).get_selected_label()
            if not label:
                self.notify("No label selected", severity="warning")
                return
            name = str(label.get("name", ""))
            await self._run_jql_context(
                f'project = {self.project_key} AND labels = "{name}"',
                f"Source: issues with label {name}",
            )
            return

        if self.active_kind == "versions":
            version = self.query_one("#version_table", VersionTableWidget).get_selected_version()
            if not version:
                self.notify("No version selected", severity="warning")
                return
            name = str(version.get("name", ""))
            field = "milestone" if self.context.provider == "github" else "fixVersion"
            await self._run_jql_context(
                f'project = {self.project_key} AND {field} = "{name}"',
                f"Source: issues in {name}",
            )
            return

        if self.active_kind == "users":
            user = self.query_one("#user_table", UserTableWidget).get_selected_user()
            if not user:
                self.notify("No user selected", severity="warning")
                return
            self.push_screen(
                UserIssuesModal(str(user.get("displayName") or user.get("accountId") or "user")),
                lambda dimension: self.run_worker(self._show_user_issues(user, dimension), exclusive=True)
                if dimension
                else None,
            )

    async def _show_user_issues(self, user: dict, dimension: str) -> None:
        """Show issues assigned to or reported by the selected user."""
        account_id = str(user.get("accountId") or user.get("displayName") or "")
        display_name = str(user.get("displayName") or account_id)
        await self._run_jql_context(
            f'project = {self.project_key} AND {dimension} = "{account_id}"',
            f"Source: issues where {dimension} is {display_name}",
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
        mention_users = self._load_mention_users()
        self.push_screen(
            CommentModal(issue.key, self.comment_feature.thread_view(issue.key), mention_users=mention_users),
            lambda text: self.run_worker(self._submit_comment(text), exclusive=True) if text else None,
        )

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

    def action_issue_actions(self) -> None:
        """Open the bundled action chooser for the selected issue."""
        if self.active_kind != "issues" or not self._selected_issue():
            self.notify("No issue selected", severity="warning")
            return
        self.push_screen(IssueActionsModal(), self._handle_issue_action)

    def _handle_issue_action(self, action: str | None) -> None:
        if action == "transition":
            self.action_transition()
        elif action == "assign":
            self.action_assign()
        elif action == "edit":
            self.action_edit_resource()
        elif action == "comment":
            self.action_comment()
        elif action == "parent":
            self.run_worker(self.action_drill_up(), exclusive=True)
        elif action == "children":
            self.run_worker(self.action_drill_down(), exclusive=True)

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
            "[cyan]x[/cyan]        Issue actions\n"
            "[cyan]Enter[/cyan]    Execute active query input\n"
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

