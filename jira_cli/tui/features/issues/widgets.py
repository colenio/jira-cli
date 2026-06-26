"""Issue table/detail widgets used by the Jira TUI app."""

from textual.widgets import DataTable, Static

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

    def replace_rows(self, rows: list[IssueRow], preferred_key: str | None = None) -> IssueRow | None:
        """Replace table rows and keep selection if possible."""
        self.issues = rows
        self.clear()

        for issue in rows:
            self.add_row(
                f"{issue.issue_type_emoji} {issue.issue_type}".strip(),
                issue.key,
                issue.summary[:46] if len(issue.summary) > 46 else issue.summary,
                issue.status or "—",
                issue.assignee or "—",
                issue.priority or "—",
                key=issue.key,
            )

        if not rows:
            return None

        selected_index = 0
        if preferred_key:
            for index, issue in enumerate(rows):
                if issue.key == preferred_key:
                    selected_index = index
                    break

        try:
            self.move_cursor(row=selected_index, column=0)
        except Exception:
            # Fallback for Textual versions where move_cursor may differ.
            pass

        return rows[selected_index]


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
        self.comment_text = ""
        self.comment_position = ""

    def render(self) -> str:
        """Render the issue details."""
        if not self.issue:
            return "[dim]Select an issue to view details[/dim]"

        return (
            f"{self._render_header()}\n"
            f"{self._render_metadata()}\n"
            f"{self._render_hierarchy()}\n"
            f"{self._render_comment()}"
        )

    def _render_header(self) -> str:
        """Render the detail header line."""
        return f"[bold cyan]{self.issue.key}[/bold cyan] — {self.issue.summary}"

    def _render_metadata(self) -> str:
        """Render metadata line."""
        return (
            f"[dim]Type:[/dim] {self.issue.issue_type_emoji} {self.issue.issue_type or '—'} | "
            f"[dim]Status:[/dim] {self.issue.status or '—'} | "
            f"[dim]Assignee:[/dim] {self.issue.assignee or 'Unassigned'} | "
            f"[dim]Priority:[/dim] {self.issue.priority or '—'}"
        )

    def _render_hierarchy(self) -> str:
        """Render parent/child relationship line."""
        child_keys = ", ".join(self.issue.child_keys) if self.issue.child_keys else "—"
        return (
            f"[dim]Parent:[/dim] {self.issue.parent_key or '—'} | "
            f"[dim]Children:[/dim] {child_keys}"
        )

    def _render_comment(self) -> str:
        """Render active comment view."""
        comment_text = self.comment_text or "[dim]No comment selected[/dim]"
        return f"[dim]Comment:[/dim] {self.comment_position}\n{comment_text}"

    def update_issue(self, issue: IssueRow | None, comment_text: str = "", comment_position: str = "") -> None:
        """Update displayed issue."""
        self.issue = issue
        self.comment_text = comment_text
        self.comment_position = comment_position
        self.update(self.render())
