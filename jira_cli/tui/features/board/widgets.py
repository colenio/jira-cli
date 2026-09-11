"""Board widget: poor-man's kanban board grouped by issue status."""

from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Label, ListItem, ListView

from jira_cli.models import IssueRow

from .service import DEFAULT_STATUS_ORDER, group_by_status


def _row_label(issue: IssueRow) -> str:
    """Render a single compact board card line for an issue."""
    marker = f"{issue.issue_type_emoji} " if issue.issue_type_emoji else ""
    summary = issue.summary[:32] if len(issue.summary) > 32 else issue.summary
    return f"{marker}{issue.key}  {summary}"


class BoardColumn(VerticalScroll):
    """A single status column containing a header and a list of issue cards."""

    DEFAULT_CSS = """
    BoardColumn {
        width: 1fr;
        border: solid $accent;
        margin: 0 1 0 0;
    }
    BoardColumn > Label {
        background: $accent;
        color: $text;
        text-style: bold;
        padding: 0 1;
    }
    """

    def __init__(self, status: str, issues: list[IssueRow], **kwargs):
        super().__init__(**kwargs)
        self.status = status
        self.column_issues = issues

    def compose(self):
        """Render the column header and its issue list."""
        yield Label(f"{self.status} ({len(self.column_issues)})")
        list_view = ListView(*[self._make_item(issue) for issue in self.column_issues])
        yield list_view

    @staticmethod
    def _make_item(issue: IssueRow) -> ListItem:
        item = ListItem(Label(_row_label(issue)))
        item.issue = issue
        return item


class BoardWidget(Horizontal):
    """Kanban-style board grouping loaded issues into columns by status."""

    def __init__(
        self,
        issues: list[IssueRow],
        status_order: list[str] | None = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.status_order = status_order if status_order is not None else DEFAULT_STATUS_ORDER
        self.all_issues = issues

    def compose(self):
        """Render one column per distinct status."""
        for status, rows in group_by_status(self.all_issues, self.status_order).items():
            yield BoardColumn(status, rows)

    def get_selected_issue(self) -> IssueRow | None:
        """Return the issue currently highlighted in whichever column has focus."""
        focused = self.screen.focused
        if isinstance(focused, ListView) and focused.highlighted_child:
            return getattr(focused.highlighted_child, "issue", None)
        return None

    async def replace_rows(self, rows: list[IssueRow], preferred_key: str | None = None) -> IssueRow | None:
        """Rebuild all columns from the given rows, restoring selection if possible."""
        self.all_issues = rows
        for column in list(self.children):
            await column.remove()

        columns = group_by_status(rows, self.status_order)
        for status, col_rows in columns.items():
            await self.mount(BoardColumn(status, col_rows))

        return self._select_issue(preferred_key)

    def _select_issue(self, preferred_key: str | None) -> IssueRow | None:
        """Highlight preferred_key if present, else the first card in the first column."""
        fallback: tuple[ListView, IssueRow] | None = None
        for column in self.children:
            if not isinstance(column, BoardColumn):
                continue
            list_view = column.query(ListView).first()
            if list_view is None or not list_view.children:
                continue
            if fallback is None:
                fallback = (list_view, list_view.children[0].issue)
            if preferred_key:
                for index, item in enumerate(list_view.children):
                    if getattr(item, "issue", None) and item.issue.key == preferred_key:
                        list_view.index = index
                        return item.issue

        if fallback:
            list_view, issue = fallback
            list_view.index = 0
            return issue
        return None

    def focus_board(self) -> None:
        """Focus the first available issue card."""
        for column in self.children:
            if not isinstance(column, BoardColumn):
                continue
            list_view = column.query(ListView).first()
            if list_view is not None and list_view.children:
                list_view.focus()
                return
