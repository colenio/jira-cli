"""Command bar, workflow submission, and quick-filter actions."""

from __future__ import annotations

from rich.markup import escape
from textual.widgets import Input, Label

from jira_cli.query import JiraQuery, order_by_clause
from jira_cli.tui.features.query.service import QUICK_FILTER_DIMENSIONS, parse_command, resolve_bare_quick_filter
from jira_cli.tui.features.workflow.suggester import ActionSuggester


class WorkflowControllerMixin:
    """Own command input dispatch and issue workflow submissions."""

    async def _submit_transition(self, expression: str) -> None:
        issue_key = self.pending_issue_key
        transition_id = self.pending_transition_id
        choice_map = self.transition_choice_map
        self.pending_transition_id = ""

        def run_transition():
            message = self.workflow_feature.submit_transition_expression(issue_key, expression, choice_map, default_transition_id=transition_id)
            return message, self._run_remote_query()

        def on_done(worker) -> None:
            if worker.result:
                message, rows = worker.result
                self.all_issues = rows
                self.notify(message)
                self.run_worker(self._apply_filter(self.query_one("#filter_input", Input).value), exclusive=True)
                self._restore_active_focus(preferred_key=issue_key)

        self.run_worker(run_transition, thread=True, exclusive=True, exit_on_error=False, callback=on_done)

    async def _submit_assign(self, expression: str) -> None:
        issue_key = self.pending_issue_key

        def run_assign():
            message = self.workflow_feature.submit_assign_expression(issue_key, expression)
            return message, self._run_remote_query()

        def on_done(worker) -> None:
            if worker.result:
                message, rows = worker.result
                self.all_issues = rows
                self.notify(message)
                self.run_worker(self._apply_filter(self.query_one("#filter_input", Input).value), exclusive=True)
                self._restore_active_focus(preferred_key=issue_key)

        self.run_worker(run_assign, thread=True, exclusive=True, exit_on_error=False, callback=on_done)

    async def _submit_edit_title(self, expression: str) -> None:
        title = expression.strip()
        if not title:
            self.notify("Title is empty", severity="warning")
            return
        issue_key = self.pending_issue_key
        self.client.update_issue(issue_key, {"summary": title})
        self.notify(f"Updated title for {issue_key}")
        await self.action_refresh()

    async def _submit_edit_fields(self, fields: dict) -> None:
        if not fields.get("summary"):
            self.notify("Title is empty", severity="warning")
            return
        self.client.update_issue(self.pending_issue_key, {key: value for key, value in fields.items() if key != "action"})
        self.notify(f"Updated {self.pending_issue_key}")
        await self.action_refresh()

    async def _submit_comment(self, expression: str) -> None:
        try:
            message = self.comment_feature.submit_comment_expression(self.pending_issue_key, expression)
        except ValueError as value_error:
            self.notify(str(value_error), severity="error")
            return
        self.notify(message)
        self.comment_feature.invalidate_issue(self.pending_issue_key)
        await self.action_refresh()

    async def _submit_by_mode(self, expression: str) -> None:
        handlers = {
            "find": self._submit_find,
            "jql": self._submit_jql,
            "command": self._submit_command,
            "transition": self._submit_transition,
            "assign": self._submit_assign,
            "edit_title": self._submit_edit_title,
            "comment": self._submit_comment,
        }
        handler = handlers.get(self.input_mode)
        if handler:
            await handler(expression)
        else:
            self.notify("No active input mode", severity="warning")

    async def on_input_submitted(self, event: Input.Submitted) -> None:
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
        except Exception as error:
            self.notify(f"Query failed: {escape(str(error))}", severity="error")
        finally:
            self._restore_active_focus(preferred_key=preferred_key)

    def action_focus_filter(self) -> None:
        self._show_filter_input()

    def action_focus_command(self) -> None:
        self.input_mode = "command"
        self.query_one("#mode_context", Label).update("MODE: COMMAND (INPUT)")
        query_input = self.query_one("#query_input", Input)
        query_input.suggester = self.command_suggester
        self._show_query_input("table/board/users/labels/versions | actions/create/edit/related | status= | assignee= | label= | clear")

    async def _submit_command(self, expression: str) -> None:
        verb, arg = parse_command(expression)
        if verb in ("table", "issues"):
            self._show_resource("issues", board=False); return
        if verb in ("board", "b"):
            self._show_resource("issues", board=True); return
        if verb in ("v", "view", "open"):
            self.action_open_issue(); return
        if verb == "create":
            if self.check_action("create_resource", ()): self.action_create_resource()
            else: self.notify("Create is not available in this context", severity="warning")
            return
        if verb == "edit":
            if self.check_action("edit_resource", ()): self.action_edit_resource()
            else: self.notify("Edit is not available in this context", severity="warning")
            return
        if verb == "delete":
            if self.check_action("delete_resource", ()): self.action_delete_resource()
            else: self.notify("Delete is not available in this context", severity="warning")
            return
        if verb == "related":
            await self.action_issues_for_resource(); return
        if verb == "next":
            issue = self._selected_issue()
            try:
                context = self.workflow_feature.prepare_next_transition_action(issue, self._status_order())
            except ValueError as value_error:
                self.notify(str(value_error), severity="warning"); return
            self.pending_issue_key = context.issue_key
            self.pending_transition_id = context.default_transition_id
            self.input_mode = context.input_mode
            self.query_one("#mode_context", Label).update(context.mode_label)
            self.transition_choice_map = context.choice_map
            self.notify(context.notice, timeout=8)
            self._show_query_input(context.placeholder); return
        if verb == "clear":
            self.type_filter = self.status_filter = self.assignee_filter = self.label_filter = self.priority_filter = ""
            self.key_filter = self.order_by = ""
            self.quick_filter_clauses.clear()
            await self._run_combined_quick_filters("Quick filters cleared"); return
        if verb == "me":
            self._show_current_user(); return
        if verb == "users":
            self._show_assignable_users(); return
        if verb == "labels":
            self._show_labels(); return
        if verb == "user":
            if not arg: self.notify("Usage: user=<query>", severity="warning")
            else: self._show_user_search(arg)
            return
        if verb in {"versions", "milestones"}:
            self._show_versions("Milestones" if verb == "milestones" else "Versions"); return
        if verb == "order":
            if not arg: self.notify("Usage: order=<field> [asc|desc]", severity="warning"); return
            if arg.strip().lower() == "clear":
                self.order_by = ""; await self._run_combined_quick_filters("Order cleared"); return
            order_by_clause(arg); self.order_by = arg
            await self._run_combined_quick_filters(f"Order={arg}"); return
        if verb == "overdue":
            mine = arg.strip().lower() == "me"
            await self._run_jql_context(JiraQuery.overdue_jql(self.project_key, mine=mine), f"Source: overdue{' (mine)' if mine else ''}"); return
        if verb in QUICK_FILTER_DIMENSIONS:
            if not arg: self.notify(f"Usage: {verb}=<value>", severity="warning"); return
            await self._apply_quick_filter(verb, arg); return
        resolved = resolve_bare_quick_filter(self.all_issues, expression)
        if resolved:
            await self._apply_quick_filter(*resolved); return
        self.notify(f"Unknown command: {expression}", severity="warning")

    async def _apply_quick_filter(self, dimension: str, value: str) -> None:
        distinct_fn, attr = QUICK_FILTER_DIMENSIONS[dimension]
        display_value, clause = self.quick_filter_resolver.resolve(dimension, value, distinct_fn(self.all_issues))
        if not display_value:
            self.notify(f"Usage: {dimension}=<value>", severity="warning"); return
        setattr(self, attr, display_value)
        self.quick_filter_clauses[dimension] = clause
        await self._run_combined_quick_filters(f"{dimension.capitalize()}={display_value}")

    async def _run_combined_quick_filters(self, message: str) -> None:
        clauses = " AND ".join(self.quick_filter_clauses.values())
        jql = f"project = {self.project_key}" + (f" AND {clauses}" if clauses else "")
        order_clause = order_by_clause(self.order_by)
        if order_clause: jql = f"{jql} {order_clause}"
        await self._run_jql_context(jql, f"Source: {self.query_language.lower()} {jql}")
        self.notify(message)
