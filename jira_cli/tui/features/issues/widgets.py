"""Issue table/detail widgets used by the Jira TUI app."""

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import DataTable, Markdown

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


class IssueDetailWidget(VerticalScroll):
    """Display details of the selected issue."""

    DEFAULT_CSS = """
    IssueDetailWidget {
        border: solid $accent;
        height: 1fr;
        overflow-y: auto;
        color: $text;
    }
    #issue_detail_body {
        height: auto;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.issue = None
        self.comment_text = ""
        self.comment_position = ""

    def compose(self) -> ComposeResult:
        yield Markdown("", id="issue_detail_body", open_links=False)

    def _render_body(self) -> str:
        """Render the issue details."""
        if not self.issue:
            return "[dim]Select an issue to view details[/dim]"

        return (
            f"{self._render_header()}\n\n---\n\n"
            f"{self._render_metadata()}\n\n---\n\n"
            f"{self._render_description()}\n\n---\n\n"
            f"{self._render_comment()}"
        )

    def _render_header(self) -> str:
        """Render the detail header line."""
        return f"**`{self.issue.key}`** — {self.issue.summary}"

    def _render_metadata(self) -> str:
        """Render metadata line."""
        return (
            f"**Type:** {self.issue.issue_type_emoji} {self.issue.issue_type or '—'}  \n"
            f"**Status:** {self.issue.status or '—'}  \n"
            f"**Assignee:** {self.issue.assignee or 'Unassigned'}  \n"
            f"**Priority:** {self.issue.priority or '—'}  \n"
            f"**Labels:** {self.issue.labels or '—'}  \n"
            f"**Versions:** {self.issue.versions or '—'}  \n"
            f"{self._render_hierarchy()}"
        )

    def _render_description(self) -> str:
        """Render the issue description unchanged as its own Markdown block."""
        description = self.issue.description.strip() if self.issue.description else ""
        if not description:
            return "> No description provided."
        return description

    def _render_hierarchy(self) -> str:
        """Render parent/child relationship line."""
        if self.issue.child_keys:
            children = ", ".join(self.issue.child_keys)
        elif not self.issue.children_loaded:
            children = "loading..."
        else:
            children = "—"
        return f"**Parent:** {self.issue.parent_key or '—'}  \n**Children:** {children}"

    def _render_comment(self) -> str:
        """Render active comment view."""
        comment_text = self.comment_text or "No comments"
        position = f" ({self.comment_position.split('/')[-1]} total)" if self.comment_position else ""
        return f"## Comments{position}\n\n{comment_text}"

    def update_issue(self, issue: IssueRow | None, comment_text: str = "", comment_position: str = "") -> None:
        """Update displayed issue."""
        self.issue = issue
        self.comment_text = comment_text
        self.comment_position = comment_position
        self.query_one("#issue_detail_body", Markdown).update(self._render_body())
        for button in self.query("#issue_detail_actions Button"):
            button.disabled = issue is None
