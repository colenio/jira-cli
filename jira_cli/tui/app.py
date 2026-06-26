"""Main Textual application for interactive Jira issue management."""

import webbrowser
from typing import Literal

from textual.app import ComposeResult, App
from textual.widgets import Label, DataTable, Footer, Header, Input
from textual.binding import Binding

from jira_cli.client import JiraClient
from jira_cli.models import IssueRow
from jira_cli.query import JiraQuery
from jira_cli.tui.features.comment import JiraCommentFeature
from jira_cli.tui.features.issues import IssueDetailWidget, IssueTableWidget
from jira_cli.tui.features.query.service import QueryMode, build_query_labels, filter_issues, run_remote_query
from jira_cli.tui.features.workflow import JiraWorkflowFeature


class JiraApp(App):
    """Main Jira TUI Application."""

    BINDINGS = [
        Binding("q", "quit", "Quit", show=True),
        Binding("p", "reset_source", "Project", show=True),
        Binding("slash", "focus_filter", "Filter", show=True),
        Binding("f", "focus_find", "Find", show=True),
        Binding("j", "focus_jql", "JQL", show=True),
        Binding("t", "transition", "Transition", show=True),
        Binding("a", "assign", "Assign", show=True),
        Binding("c", "comment", "Comment", show=True),
        Binding("n", "next_comment", "NextComment", show=True),
        Binding("b", "prev_comment", "PrevComment", show=True),
        Binding("u", "drill_up", "Parent", show=True),
        Binding("d", "drill_down", "Children", show=True),
        Binding("r", "refresh", "Refresh", show=True),
        Binding("o", "open_issue", "Open in Browser", show=True),
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

    def __init__(self, client: JiraClient, project_key: str, issues: list[IssueRow], **kwargs):
        super().__init__(**kwargs)
        self.client = client
        self.project_key = project_key
        self.all_issues = issues
        self.issues = issues
        self.query = JiraQuery(client)
        self.query_mode: QueryMode = "project"
        self.query_expression = ""
        self.last_find_expression = ""
        self.last_jql_expression = ""
        self.input_mode: Literal["find", "jql", "transition", "assign", "comment", "none"] = "none"
        self.pending_issue_key = ""
        self.transition_choice_map: dict[str, str] = {}
        self.comment_feature = JiraCommentFeature(client)
        self.workflow_feature = JiraWorkflowFeature(client)

    def compose(self) -> ComposeResult:
        """Create the app layout."""
        yield Header(show_clock=True)
        yield Label(f"[bold cyan]Jira CLI[/bold cyan] — Project: [bold yellow]{self.project_key}[/bold yellow]")
        yield Label("MODE: PROJECT", id="mode_context")
        yield Label(f"Source: project={self.project_key}", id="query_context")
        yield Input(placeholder="Find text in summary/description and press Enter", id="query_input")
        yield Input(placeholder="Filter issues (key/summary/status/assignee). Press Esc to clear", id="filter_input")
        yield IssueTableWidget(self.issues, id="issue_table")
        yield IssueDetailWidget(id="issue_detail")
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
        table.focus()
        if self.issues:
            self.update_issue_detail(self.issues[0])

    def _update_query_context(self) -> None:
        """Render active remote query context."""
        mode_text, source_text = build_query_labels(self.project_key, self.query_mode, self.query_expression)

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
            max_results=100,
        )

    def _selected_issue(self) -> IssueRow | None:
        """Return currently selected issue in table."""
        table = self.query_one("#issue_table", IssueTableWidget)
        return table.get_selected_issue()

    def _show_query_input(self, placeholder: str, value: str = "") -> None:
        """Show query input consistently and focus it."""
        query_input = self.query_one("#query_input", Input)
        query_input.disabled = False
        query_input.placeholder = placeholder
        query_input.value = value
        query_input.display = True
        query_input.focus()

    def _hide_query_input(self) -> None:
        """Hide query input and return focus to table."""
        query_input = self.query_one("#query_input", Input)
        query_input.display = False
        query_input.disabled = True
        table = self.query_one("#issue_table", IssueTableWidget)
        table.focus()

    def _show_filter_input(self) -> None:
        """Show filter input and focus it."""
        filter_input = self.query_one("#filter_input", Input)
        filter_input.disabled = False
        filter_input.display = True
        filter_input.focus()

    def _hide_filter_input(self) -> None:
        """Hide filter input and return focus to table."""
        filter_input = self.query_one("#filter_input", Input)
        filter_input.display = False
        filter_input.disabled = True
        table = self.query_one("#issue_table", IssueTableWidget)
        table.focus()

    def _run_jql_context(self, jql: str, context_label: str) -> None:
        """Execute JQL and set it as active remote context."""
        self.query_mode = "jql"
        self.query_expression = jql
        self.last_jql_expression = jql
        rows = self.query.search_custom_jql(jql, max_results=100)
        self.all_issues = rows
        self._update_query_context()
        context = self.query_one("#query_context", Label)
        context.update(context_label)
        filter_input = self.query_one("#filter_input", Input)
        self._apply_filter(filter_input.value)

    def _render_issue_table(self, rows: list[IssueRow], preferred_key: str | None = None) -> None:
        """Render rows into table and keep selection if possible."""
        table = self.query_one("#issue_table", IssueTableWidget)
        selected_issue = table.replace_rows(rows, preferred_key=preferred_key)
        if not selected_issue:
            detail = self.query_one("#issue_detail", IssueDetailWidget)
            detail.update_issue(None)
            return

        self.update_issue_detail(selected_issue)

    def _apply_filter(self, filter_text: str) -> None:
        """Apply in-memory filter to currently loaded issues."""
        table = self.query_one("#issue_table", IssueTableWidget)
        current = table.get_selected_issue()
        preferred_key = current.key if current else None

        filtered = filter_issues(self.all_issues, filter_text)

        self.issues = filtered
        self._render_issue_table(filtered, preferred_key=preferred_key)

    def on_input_changed(self, event: Input.Changed) -> None:
        """Incrementally filter table rows when filter input changes."""
        if event.input.id != "filter_input":
            return
        self._apply_filter(event.value)

    def _apply_loaded_rows(self, rows: list[IssueRow], success_message: str) -> None:
        """Update issue store and refresh table/detail with current local filter."""
        self.all_issues = rows
        self._update_query_context()
        filter_input = self.query_one("#filter_input", Input)
        self._apply_filter(filter_input.value)
        self.notify(success_message)

    def _submit_find(self, expression: str) -> None:
        """Handle submitted input in find mode."""
        self.query_mode = "find"
        self.query_expression = expression
        self.last_find_expression = expression
        rows = self._run_remote_query()
        self._apply_loaded_rows(rows, f"Loaded {len(rows)} issues")

    def _submit_jql(self, expression: str) -> None:
        """Handle submitted input in jql mode."""
        self.query_mode = "jql"
        self.query_expression = expression
        self.last_jql_expression = expression
        rows = self._run_remote_query()
        self._apply_loaded_rows(rows, f"Loaded {len(rows)} issues")

    def _submit_transition(self, expression: str) -> None:
        """Handle submitted transition command."""
        try:
            message = self.workflow_feature.submit_transition_expression(
                self.pending_issue_key,
                expression,
                self.transition_choice_map,
            )
        except ValueError as value_error:
            self.notify(str(value_error), severity="error")
            return

        self.notify(message)
        self.action_refresh()

    def _submit_assign(self, expression: str) -> None:
        """Handle submitted assign command."""
        message = self.workflow_feature.submit_assign_expression(self.pending_issue_key, expression)
        self.notify(message)
        self.action_refresh()

    def _submit_comment(self, expression: str) -> None:
        """Handle submitted comment input."""
        try:
            message = self.comment_feature.submit_comment_expression(self.pending_issue_key, expression)
        except ValueError as value_error:
            self.notify(str(value_error), severity="error")
            return

        self.notify(message)
        self.comment_feature.invalidate_issue(self.pending_issue_key)
        self.action_refresh()

    def _submit_by_mode(self, expression: str) -> None:
        """Dispatch query input submission to active input mode handler."""
        if self.input_mode == "find":
            self._submit_find(expression)
            return
        if self.input_mode == "jql":
            self._submit_jql(expression)
            return
        if self.input_mode == "transition":
            self._submit_transition(expression)
            return
        if self.input_mode == "assign":
            self._submit_assign(expression)
            return
        if self.input_mode == "comment":
            self._submit_comment(expression)
            return

        self.notify("No active input mode", severity="warning")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Run remote query when query input is submitted."""
        if event.input.id != "query_input":
            return

        expression = event.value.strip()
        if not expression:
            self.notify("Query text is empty", severity="warning")
            return

        self._hide_query_input()

        try:
            self._submit_by_mode(expression)
            self.input_mode = "none"
        except Exception as e:
            self.notify(f"Query failed: {e}", severity="error")

    def action_focus_filter(self) -> None:
        """Show and focus filter input."""
        self._show_filter_input()

    def action_focus_find(self) -> None:
        """Show and focus find query input."""
        self.input_mode = "find"
        mode_label = self.query_one("#mode_context", Label)
        mode_label.update("MODE: FIND (INPUT)")
        self._show_query_input("Find text in summary/description and press Enter", self.last_find_expression)

    def action_focus_jql(self) -> None:
        """Show and focus JQL query input."""
        self.input_mode = "jql"
        mode_label = self.query_one("#mode_context", Label)
        mode_label.update("MODE: JQL (INPUT)")
        self._show_query_input("Enter JQL and press Enter", self.last_jql_expression)

    def action_transition(self) -> None:
        """Prompt for transition ID or name and execute transition."""
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
        self.input_mode = context.input_mode
        mode_label = self.query_one("#mode_context", Label)
        mode_label.update(context.mode_label)
        self.transition_choice_map = context.choice_map

        self.notify(context.notice, timeout=8)
        self._show_query_input(context.placeholder)

    def action_assign(self) -> None:
        """Prompt for assignee and execute assignment."""
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
        self._show_query_input(context.placeholder)

    def action_comment(self) -> None:
        """Prompt for comment and execute submission with validation."""
        issue = self._selected_issue()
        try:
            context = self.comment_feature.prepare_comment_action(issue)
        except ValueError as value_error:
            self.notify(str(value_error), severity="warning")
            return

        self.pending_issue_key = context.issue_key
        self.input_mode = context.input_mode
        mode_label = self.query_one("#mode_context", Label)
        mode_label.update(context.mode_label)
        self._show_query_input(context.placeholder)

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

    def action_drill_up(self) -> None:
        """Drill up to parent issue."""
        issue = self._selected_issue()
        if not issue:
            self.notify("No issue selected", severity="warning")
            return
        if not issue.parent_key:
            self.notify(f"{issue.key} has no parent", severity="warning")
            return
        try:
            self._run_jql_context(f"key = {issue.parent_key}", f"Source: parent of {issue.key} -> {issue.parent_key}")
        except Exception as e:
            self.notify(f"Drill up failed: {e}", severity="error")

    def action_drill_down(self) -> None:
        """Drill down into child issues."""
        issue = self._selected_issue()
        if not issue:
            self.notify("No issue selected", severity="warning")
            return
        if not issue.child_keys:
            self.notify(f"{issue.key} has no child issues", severity="warning")
            return
        try:
            keys = ",".join(issue.child_keys)
            self._run_jql_context(
                f"key in ({keys}) ORDER BY key",
                f"Source: children of {issue.key} ({len(issue.child_keys)})",
            )
        except Exception as e:
            self.notify(f"Drill down failed: {e}", severity="error")

    def action_clear_filter(self) -> None:
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
            self._apply_filter("")
            self._update_query_context()
            return

        # No active input open: Esc acts as "back to project source".
        if self.query_mode != "project":
            self.action_reset_source()

    def action_reset_source(self) -> None:
        """Reset remote source context back to default project query."""
        self.query_mode = "project"
        self.query_expression = ""
        self.input_mode = "none"

        query_input = self.query_one("#query_input", Input)
        if query_input.display:
            query_input.value = ""
            self._hide_query_input()

        filter_input = self.query_one("#filter_input", Input)
        if filter_input.display:
            filter_input.value = ""
            self._hide_filter_input()

        self.action_refresh()
        self.notify(f"Source reset to project={self.project_key}")

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """Update details when row highlight changes in the issue table."""
        if event.data_table.id != "issue_table":
            return
        table = self.query_one("#issue_table", IssueTableWidget)
        selected = table.get_selected_issue()
        if selected:
            self.update_issue_detail(selected)

    def update_issue_detail(self, issue: IssueRow) -> None:
        """Update the detail view with selected issue."""
        comment_text, comment_position = self.comment_feature.current_view(issue.key)
        detail = self.query_one("#issue_detail", IssueDetailWidget)
        detail.update_issue(issue, comment_text=comment_text, comment_position=comment_position)

    def action_refresh(self) -> None:
        """Refresh the issue list."""
        try:
            rows = self._run_remote_query()
            self.all_issues = rows
            self._update_query_context()
            filter_input = self.query_one("#filter_input", Input)
            self._apply_filter(filter_input.value)
        except Exception as e:
            self.notify(f"Error refreshing: {e}", severity="error")

    def action_open_issue(self) -> None:
        """Open selected issue in browser."""
        table = self.query_one("#issue_table", IssueTableWidget)
        issue = table.get_selected_issue()
        if issue:
            try:
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
            "[cyan]j[/cyan]        Run JQL query\n"
            "[cyan]Enter[/cyan]    Execute active query input\n"
            "[cyan]t[/cyan]        Transition selected issue\n"
            "[cyan]a[/cyan]        Assign selected issue\n"
            "[cyan]c[/cyan]        Add comment (plain/md/adf)\n"
            "[cyan]n[/cyan]        Next comment\n"
            "[cyan]b[/cyan]        Previous comment\n"
            "[cyan]u[/cyan]        Drill up to parent issue\n"
            "[cyan]d[/cyan]        Drill down to child issues\n"
            "[cyan]Esc[/cyan]      Close input or reset source\n"
            "[cyan]o[/cyan]        Open in browser\n"
            "[cyan]r[/cyan]        Refresh issues\n"
            "[cyan]q[/cyan]        Quit\n"
        )
        self.notify(help_text, title="Help")


def run_tui(client: JiraClient, project_key: str) -> None:
    """Launch the TUI application."""
    query = JiraQuery(client)
    try:
        issues = query.search_project(project_key=project_key, max_results=100)
        app = JiraApp(client, project_key, issues)
        app.run()
    except Exception as e:
        print(f"Error launching TUI: {e}")
        raise

