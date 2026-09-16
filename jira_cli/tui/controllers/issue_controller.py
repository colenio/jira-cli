"""Issue-specific interactions for the TUI."""

from __future__ import annotations

import webbrowser

from rich.markup import escape
from textual.widgets import DataTable, Label, ListView

from jira_cli.models import IssueRow
from jira_cli.query import JiraQuery
from jira_cli.tui.features.board import BoardWidget
from jira_cli.tui.features.comment import JiraCommentFeature
from jira_cli.tui.features.issues import IssueDetailWidget, IssueTableWidget
from jira_cli.tui.features.issues.modals import CommentModal
from jira_cli.tui.features.labels import LabelDetailWidget, LabelTableWidget
from jira_cli.tui.features.users import UserDetailWidget, UserTableWidget
from jira_cli.tui.features.users.modals import UserIssuesModal
from jira_cli.tui.features.versions import VersionDetailWidget, VersionTableWidget
from jira_cli.tui.features.workflow.suggester import ActionSuggester


class IssueControllerMixin:
    """Own issue workflow actions, selection events, and detail refresh."""

    def action_focus_find(self) -> None:
        self.input_mode = "find"
        self.query_one("#mode_context", Label).update("MODE: FIND (INPUT)")
        query_input = self.query_one("#query_input")
        query_input.suggester = None
        self._show_query_input("Find text in summary/description and press Enter", self.last_find_expression)

    def action_focus_jql(self) -> None:
        self.input_mode = "jql"
        self.query_one("#mode_context", Label).update(f"MODE: {self.query_language.upper()} (INPUT)")
        query_input = self.query_one("#query_input")
        query_input.suggester = None
        self._show_query_input(self._provider_query_placeholder(), self.last_jql_expression)

    def _provider_query_placeholder(self) -> str:
        if self.context.provider == "github":
            return 'GitHub issue query, e.g. status = "all" AND labels = "bug" ORDER BY updated DESC'
        if self.context.provider == "demo":
            return 'Demo query, e.g. priority = "Highest" ORDER BY updated DESC'
        return f'JQL, e.g. project = {self.project_key} AND status = "In Progress" ORDER BY updated DESC'

    def action_transition(self) -> None:
        issue = self._selected_issue()
        try:
            context = self.workflow_feature.prepare_transition_action(issue)
        except ValueError as value_error:
            self.notify(str(value_error), severity="warning"); return
        except Exception as error:
            self.notify(f"Cannot load transitions: {error}", severity="error"); return
        self.pending_issue_key = context.issue_key
        self.pending_transition_id = context.default_transition_id
        self.input_mode = context.input_mode
        self.query_one("#mode_context", Label).update(context.mode_label)
        self.transition_choice_map = context.choice_map
        candidates = [key for key in context.choice_map if not key.islower() or key in context.choice_map.values()]
        self.query_one("#query_input").suggester = ActionSuggester(list(dict.fromkeys(candidates)))
        self.notify(context.notice, timeout=8)
        self._show_query_input("Transition status name or ID [| optional comment]")

    def action_assign(self) -> None:
        issue = self._selected_issue()
        try:
            context = self.workflow_feature.prepare_assign_action(issue)
        except ValueError as value_error:
            self.notify(str(value_error), severity="warning"); return
        self.pending_issue_key = context.issue_key
        self.input_mode = context.input_mode
        self.query_one("#mode_context", Label).update(context.mode_label)
        try:
            assignable = self.client.list_assignable_users(self.project_key, max_results=20)
        except Exception:
            assignable = []
        candidates = ["me"]
        labels = ["me (current user)"]
        for user in assignable:
            name = user.get("displayName") or ""
            account = user.get("accountId") or ""
            entry = name or account
            if entry:
                labels.append(f"{name} (@{account})" if name and account and name != account else entry)
                candidates.extend([name, account, f"@{account}"] if name and account else [entry, f"@{entry}"])
        self.query_one("#query_input").suggester = ActionSuggester(list(dict.fromkeys(candidates)))
        self.notify("Assignees: " + " | ".join(labels[:5]), timeout=8)
        self._show_query_input("Assignee name or @handle (press Tab for completion)")

    async def action_issues_for_resource(self) -> None:
        if self.active_kind == "labels":
            resource = self.query_one("#label_table", LabelTableWidget).get_selected_label()
            if resource:
                name = str(resource.get("name", ""))
                await self._run_jql_context(f'project = {self.project_key} AND labels = "{name}"', f"Source: issues with label {name}")
            return
        if self.active_kind == "versions":
            resource = self.query_one("#version_table", VersionTableWidget).get_selected_version()
            if resource:
                name = str(resource.get("name", ""))
                field = "milestone" if self.context.provider == "github" else "fixVersion"
                await self._run_jql_context(f'project = {self.project_key} AND {field} = "{name}"', f"Source: issues in {name}")
            return
        if self.active_kind == "users":
            user = self.query_one("#user_table", UserTableWidget).get_selected_user()
            if user:
                self.push_screen(UserIssuesModal(str(user.get("displayName") or user.get("accountId") or "user")), lambda dimension: self.run_worker(self._show_user_issues(user, dimension), exclusive=True) if dimension else None)

    async def _show_user_issues(self, user: dict, dimension: str) -> None:
        account = str(user.get("accountId") or user.get("displayName") or "")
        await self._run_jql_context(f'project = {self.project_key} AND {dimension} = "{account}"', f"Source: issues where {dimension} is {user.get('displayName') or account}")

    def action_comment(self) -> None:
        issue = self._selected_issue()
        try:
            context = self.comment_feature.prepare_comment_action(issue)
        except ValueError as value_error:
            self.notify(str(value_error), severity="warning"); return
        self.pending_issue_key = context.issue_key
        self.push_screen(CommentModal(issue.key, self.comment_feature.thread_view(issue.key), mention_users=self._load_mention_users()), lambda text: self.run_worker(self._submit_comment(text), exclusive=True) if text else None)

    async def action_drill_up(self) -> None:
        issue = self._selected_issue()
        if not issue:
            self.notify("No issue selected", severity="warning"); return
        if not issue.parent_key:
            self.notify(f"{issue.key} has no parent", severity="warning"); return
        try:
            await self._run_jql_context(f"key = {issue.parent_key}", f"Source: parent of {issue.key} -> {issue.parent_key}")
        except Exception as error:
            self.notify(f"Drill up failed: {error}", severity="error")

    async def action_drill_down(self) -> None:
        issue = self._selected_issue()
        if not issue:
            self.notify("No issue selected", severity="warning"); return
        try:
            if issue.child_keys and issue.issue_type.casefold() != "epic":
                keys = ",".join(issue.child_keys)
                await self._run_jql_context(f"key in ({keys}) ORDER BY key", f"Source: children of {issue.key} ({len(issue.child_keys)})")
                return
            await self._run_jql_context(JiraQuery.children_jql(issue.key), f"Source: children of {issue.key}")
            if not self.all_issues:
                self.notify(f"{issue.key} has no child issues", severity="warning")
        except Exception as error:
            self.notify(f"Drill down failed: {error}", severity="error")

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.data_table.id == "user_table":
            self.query_one("#user_detail", UserDetailWidget).update_user(self.query_one("#user_table", UserTableWidget).get_selected_user()); return
        if event.data_table.id == "version_table":
            self.query_one("#version_detail", VersionDetailWidget).update_version(self.query_one("#version_table", VersionTableWidget).get_selected_version()); return
        if event.data_table.id == "label_table":
            self.query_one("#label_detail", LabelDetailWidget).update_label(self.query_one("#label_table", LabelTableWidget).get_selected_label()); return
        if event.data_table.id == "issue_table":
            issue = self.query_one("#issue_table", IssueTableWidget).get_selected_issue()
            if issue:
                self.update_issue_detail(issue); self._prefetch_comments_for_issue(issue); self._children_prefetch.prefetch(issue)

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if self.board_visible and event.item is not None:
            issue = getattr(event.item, "issue", None)
            if issue:
                self.update_issue_detail(issue); self._prefetch_comments_for_issue(issue); self._children_prefetch.prefetch(issue)

    def update_issue_detail(self, issue: IssueRow) -> None:
        comment_text, comment_position = self.comment_feature.cached_thread_view(issue.key)
        self.query_one("#issue_detail", IssueDetailWidget).update_issue(issue, comment_text=comment_text, comment_position=comment_position)

    def action_open_issue(self) -> None:
        if self.context.provider == "demo":
            self.notify("Browser opening disabled in demo mode", severity="warning"); return
        issue = self._selected_issue()
        if not issue:
            self.notify("No issue selected", severity="warning"); return
        try:
            url = self.client.get_issue_url(issue.key) if hasattr(self.client, "get_issue_url") else f"{self.client.base_url.rstrip('/')}/browse/{issue.key}"
            webbrowser.open(url); self.notify(f"Opened {issue.key} in browser")
        except Exception as error:
            self.notify(f"Error: {error}", severity="error")
