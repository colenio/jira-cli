"""Issue query, filtering, and result rendering controller actions."""

from __future__ import annotations

from textual.widgets import Input

from jira_cli.models import IssueRow
from jira_cli.query import JiraQuery
from jira_cli.quick_filters import normalize_for_match
from jira_cli.tui.features.issues import IssueDetailWidget, IssueTableWidget
from jira_cli.tui.features.labels import LabelDetailWidget, LabelTableWidget
from jira_cli.tui.features.query.service import filter_issues, run_remote_query
from jira_cli.tui.features.users import UserDetailWidget, UserTableWidget
from jira_cli.tui.features.versions import VersionDetailWidget, VersionTableWidget


class QueryControllerMixin:
    """Own remote query result loading and local resource filtering."""

    def _run_remote_query(self) -> list[IssueRow]:
        """Run the currently active remote query source."""
        return run_remote_query(
            query=self.query,
            project_key=self.project_key,
            query_mode=self.query_mode,
            query_expression=self.query_expression,
            order_by=self.order_by,
            max_results=100,
        )

    async def _run_jql_context(self, jql: str, context_label: str) -> None:
        """Execute a provider query and set it as the active remote context."""
        self.query_mode = "jql"
        self.query_expression = jql
        self.last_jql_expression = jql
        rows = self.query.search_custom_jql(jql, max_results=100)
        self.all_issues = rows
        self._show_resource("issues", board=self.board_visible)
        self._update_query_context()
        self.query_one("#query_context", object).update(context_label)
        filter_input = self.query_one("#filter_input", Input)
        await self._apply_filter(filter_input.value)

    async def _render_issue_table(self, rows: list[IssueRow], preferred_key: str | None = None) -> None:
        """Render rows into table and board views, keeping selection if possible."""
        table = self.query_one("#issue_table", IssueTableWidget)
        table_selected = table.replace_rows(rows, preferred_key=preferred_key)
        board = self.query_one("#issue_board")
        board_selected = await board.replace_rows(rows, preferred_key=preferred_key)
        selected_issue = board_selected if self.board_visible else table_selected
        if not selected_issue:
            self.query_one("#issue_detail", IssueDetailWidget).update_issue(None)
            return
        self.update_issue_detail(selected_issue)
        self._prefetch_comments_for_issue(selected_issue)
        self._children_prefetch.prefetch(selected_issue)
        if self.timeline_visible:
            self.query_one("#issue_timeline").update_items(self._timeline_items())

    async def _apply_filter(self, filter_text: str) -> None:
        """Apply the live filter to the active resource view."""
        query = normalize_for_match(filter_text)
        if self.active_kind == "users":
            if query == "me":
                query = normalize_for_match(self.current_user_display_name)
            users = [
                user for user in self.users
                if not query
                or query in normalize_for_match(str(user.get("displayName", "")))
                or query in normalize_for_match(str(user.get("emailAddress", "")))
                or query in normalize_for_match(str(user.get("accountId", "")))
            ]
            selected = self.query_one("#user_table", UserTableWidget).replace_rows(users)
            self.query_one("#user_detail", UserDetailWidget).update_user(selected)
            return
        if self.active_kind == "versions":
            versions = [
                version for version in self.versions
                if not query
                or query in normalize_for_match(str(version.get("name", "")))
                or query in normalize_for_match("released" if version.get("released") else "unreleased")
                or query in normalize_for_match(str(version.get("releaseDate", "")))
            ]
            selected = self.query_one("#version_table", VersionTableWidget).replace_rows(versions)
            self.query_one("#version_detail", VersionDetailWidget).update_version(selected)
            return
        if self.active_kind == "labels":
            labels = [
                label for label in self.labels
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
        self.issues = filter_issues(self.all_issues, filter_text)
        await self._render_issue_table(self.issues, preferred_key=preferred_key)

    async def on_input_changed(self, event: Input.Changed) -> None:
        """Incrementally filter table rows when the filter input changes."""
        if event.input.id == "filter_input":
            await self._apply_filter(event.value)

    async def _apply_loaded_rows(self, rows: list[IssueRow], success_message: str) -> None:
        """Update issue data and refresh the current local filter."""
        self.all_issues = rows
        self._show_resource("issues", board=self.board_visible)
        self._update_query_context()
        filter_input = self.query_one("#filter_input", Input)
        await self._apply_filter(filter_input.value)
        self.notify(success_message)

    async def _submit_find(self, expression: str) -> None:
        """Handle submitted find input."""
        self.query_mode = "find"
        self.query_expression = expression
        self.last_find_expression = expression
        rows = self._run_remote_query()
        await self._apply_loaded_rows(rows, f"Loaded {len(rows)} issues")

    async def _submit_jql(self, expression: str) -> None:
        """Handle submitted provider query input."""
        self.query_mode = "jql"
        self.query_expression = expression
        self.last_jql_expression = expression
        rows = self._run_remote_query()
        await self._apply_loaded_rows(rows, f"Loaded {len(rows)} issues")
