"""Main Textual application for interactive Jira issue management."""

import webbrowser
from typing import Literal

from textual.app import ComposeResult, App
from textual.widgets import Static, Label, DataTable, Footer, Header, Input
from textual.binding import Binding

from jira_cli.client import JiraClient
from jira_cli.query import JiraQuery
from jira_cli.models import IssueRow


class IssueTableWidget(DataTable):
    """Interactive table displaying Jira issues."""

    def __init__(self, issues: list[IssueRow], **kwargs):
        super().__init__(**kwargs)
        self.issues = issues

    def on_mount(self) -> None:
        """Configure the table on mount."""
        self.add_columns("Type", "Key", "Summary", "Status", "Assignee", "Priority")
        self.cursor_type = "row"
        
        for issue in self.issues:
            self.add_row(
                f"{issue.issue_type_emoji} {issue.issue_type}".strip(),
                issue.key,
                issue.summary[:46] if len(issue.summary) > 46 else issue.summary,
                issue.status or "—",
                issue.assignee or "—",
                issue.priority or "—",
                key=issue.key,
            )

    def get_selected_issue(self) -> IssueRow | None:
        """Get the currently selected issue."""
        if self.cursor_row >= 0 and self.cursor_row < len(self.issues):
            return self.issues[self.cursor_row]
        return None


class IssueDetailWidget(Static):
    """Display details of the selected issue."""

    DEFAULT_CSS = """
    IssueDetailWidget {
        border: solid $accent;
        height: 8;
        color: $text;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.issue = None

    def render(self) -> str:
        """Render the issue details."""
        if not self.issue:
            return "[dim]Select an issue to view details[/dim]"

        return (
            f"[bold cyan]{self.issue.key}[/bold cyan] — {self.issue.summary}\n"
            f"[dim]Type:[/dim] {self.issue.issue_type_emoji} {self.issue.issue_type or '—'} | "
            f"[dim]Status:[/dim] {self.issue.status or '—'} | "
            f"[dim]Assignee:[/dim] {self.issue.assignee or 'Unassigned'} | "
            f"[dim]Priority:[/dim] {self.issue.priority or '—'}\n"
            f"[dim]Parent:[/dim] {self.issue.parent_key or '—'} | "
            f"[dim]Children:[/dim] {', '.join(self.issue.child_keys) if self.issue.child_keys else '—'}"
        )

    def update_issue(self, issue: IssueRow | None) -> None:
        """Update displayed issue."""
        self.issue = issue
        self.update(self.render())


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
        self.query_mode: Literal["project", "find", "jql"] = "project"
        self.query_expression = ""
        self.last_find_expression = ""
        self.last_jql_expression = ""
        self.input_mode: Literal["find", "jql", "transition", "assign", "none"] = "none"
        self.pending_issue_key = ""
        self.transition_choice_map: dict[str, str] = {}

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
        mode_label = self.query_one("#mode_context", Label)
        mode_label.update(f"MODE: {self.query_mode.upper()}")

        context = self.query_one("#query_context", Label)
        if self.query_mode == "project":
            context.update(f"Source: project={self.project_key}")
        elif self.query_mode == "find":
            context.update(f"Source: find \"{self.query_expression}\"")
        else:
            snippet = self.query_expression.strip().replace("\n", " ")
            if len(snippet) > 80:
                snippet = f"{snippet[:77]}..."
            context.update(f"Source: jql {snippet}")

    def _run_remote_query(self) -> list[IssueRow]:
        """Run currently selected remote query source."""
        if self.query_mode == "find":
            return self.query.find_by_text(self.project_key, self.query_expression, max_results=100)
        if self.query_mode == "jql":
            return self.query.search_custom_jql(self.query_expression, max_results=100)
        return self.query.search_project(project_key=self.project_key, max_results=100)

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
        table.issues = rows
        table.clear()

        for issue in rows:
            table.add_row(
                f"{issue.issue_type_emoji} {issue.issue_type}".strip(),
                issue.key,
                issue.summary[:46] if len(issue.summary) > 46 else issue.summary,
                issue.status or "—",
                issue.assignee or "—",
                issue.priority or "—",
                key=issue.key,
            )

        if not rows:
            detail = self.query_one("#issue_detail", IssueDetailWidget)
            detail.update_issue(None)
            return

        selected_index = 0
        if preferred_key:
            for index, issue in enumerate(rows):
                if issue.key == preferred_key:
                    selected_index = index
                    break

        try:
            table.move_cursor(row=selected_index, column=0)
        except Exception:
            # Fallback for Textual versions where move_cursor may differ.
            pass

        self.update_issue_detail(rows[selected_index])

    def _apply_filter(self, filter_text: str) -> None:
        """Apply in-memory filter to currently loaded issues."""
        table = self.query_one("#issue_table", IssueTableWidget)
        current = table.get_selected_issue()
        preferred_key = current.key if current else None

        query_text = (filter_text or "").strip().lower()
        if not query_text:
            filtered = self.all_issues
        else:
            filtered = [
                issue
                for issue in self.all_issues
                if query_text in issue.key.lower()
                or query_text in issue.summary.lower()
                or query_text in (issue.status or "").lower()
                or query_text in (issue.assignee or "").lower()
                or query_text in (issue.priority or "").lower()
            ]

        self.issues = filtered
        self._render_issue_table(filtered, preferred_key=preferred_key)

    def on_input_changed(self, event: Input.Changed) -> None:
        """Incrementally filter table rows when filter input changes."""
        if event.input.id != "filter_input":
            return
        self._apply_filter(event.value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Run remote query when query input is submitted."""
        if event.input.id != "query_input":
            return

        expression = event.value.strip()
        if not expression:
            self.notify("Query text is empty", severity="warning")
            return

        query_input = self.query_one("#query_input", Input)
        self._hide_query_input()

        try:
            if self.input_mode == "find":
                self.query_mode = "find"
                self.query_expression = expression
                self.last_find_expression = expression
                rows = self._run_remote_query()
                self.all_issues = rows
                self._update_query_context()
                filter_input = self.query_one("#filter_input", Input)
                self._apply_filter(filter_input.value)
                self.notify(f"Loaded {len(rows)} issues")
            elif self.input_mode == "jql":
                self.query_mode = "jql"
                self.query_expression = expression
                self.last_jql_expression = expression
                rows = self._run_remote_query()
                self.all_issues = rows
                self._update_query_context()
                filter_input = self.query_one("#filter_input", Input)
                self._apply_filter(filter_input.value)
                self.notify(f"Loaded {len(rows)} issues")
            elif self.input_mode == "transition":
                transition_input = expression
                comment = ""
                if "|" in expression:
                    left, right = expression.split("|", 1)
                    transition_input = left.strip()
                    comment = right.strip()
                transition_id = self.transition_choice_map.get(transition_input)
                if not transition_id:
                    transition_id = self.transition_choice_map.get(transition_input.lower())
                if not transition_id:
                    self.notify("Unknown transition. Use shown ID or exact name.", severity="error")
                    return
                self.client.transition_issue(self.pending_issue_key, transition_id, comment=comment or None)
                self.notify(f"Transitioned {self.pending_issue_key}")
                self.action_refresh()
            elif self.input_mode == "assign":
                self.client.assign_issue(self.pending_issue_key, expression)
                self.notify(f"Assigned {self.pending_issue_key} to {expression}")
                self.action_refresh()
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
        if not issue:
            self.notify("No issue selected", severity="warning")
            return

        try:
            transitions = self.client.get_transitions(issue.key)
        except Exception as e:
            self.notify(f"Cannot load transitions: {e}", severity="error")
            return

        if not transitions:
            self.notify(f"No transitions available for {issue.key}", severity="warning")
            return

        self.pending_issue_key = issue.key
        self.input_mode = "transition"
        mode_label = self.query_one("#mode_context", Label)
        mode_label.update("MODE: TRANSITION (INPUT)")
        self.transition_choice_map = {}
        transition_labels: list[str] = []
        for transition in transitions:
            transition_id = str(transition.get("id", "")).strip()
            transition_name = str(transition.get("name", "")).strip()
            if not transition_id:
                continue
            self.transition_choice_map[transition_id] = transition_id
            if transition_name:
                self.transition_choice_map[transition_name.lower()] = transition_id
            transition_labels.append(f"{transition_id}:{transition_name}")

        self.notify("Transitions: " + " | ".join(transition_labels), timeout=8)
        self._show_query_input("Transition ID or name; optional comment with: <transition> | <comment>")

    def action_assign(self) -> None:
        """Prompt for assignee and execute assignment."""
        issue = self._selected_issue()
        if not issue:
            self.notify("No issue selected", severity="warning")
            return
        self.pending_issue_key = issue.key
        self.input_mode = "assign"
        mode_label = self.query_one("#mode_context", Label)
        mode_label.update("MODE: ASSIGN (INPUT)")
        self._show_query_input("Assignee (email/account) and press Enter")

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
        detail = self.query_one("#issue_detail", IssueDetailWidget)
        detail.update_issue(issue)

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

