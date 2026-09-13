"""Label table/detail widgets for the TUI."""

from textual.widgets import DataTable, Static


class LabelTableWidget(DataTable):
    """Interactive table displaying labels/tags."""

    def __init__(self, labels: list[dict], **kwargs):
        super().__init__(**kwargs)
        self.labels = labels

    def on_mount(self) -> None:
        """Configure the table on mount."""
        self.add_columns("Name", "Count", "Description")
        self.cursor_type = "row"
        self._add_rows(self.labels)

    def _add_rows(self, labels: list[dict]) -> None:
        for label in labels:
            self.add_row(
                label.get("name", "?"),
                str(label.get("issueCount", "") or "-"),
                label.get("description", "") or "-",
                key=label.get("name", ""),
            )

    def replace_rows(self, labels: list[dict], preferred_key: str | None = None) -> dict | None:
        """Replace table rows and keep selection if possible."""
        self.labels = labels
        self.clear()
        self._add_rows(labels)

        if not labels:
            return None

        selected_index = 0
        if preferred_key:
            for index, label in enumerate(labels):
                if label.get("name", "") == preferred_key:
                    selected_index = index
                    break

        try:
            self.move_cursor(row=selected_index, column=0)
        except Exception:
            pass

        return labels[selected_index]

    def get_selected_label(self) -> dict | None:
        """Get the currently selected label."""
        if self.cursor_row >= 0 and self.cursor_row < len(self.labels):
            return self.labels[self.cursor_row]
        return None


class LabelDetailWidget(Static):
    """Display details for the selected label/tag."""

    DEFAULT_CSS = """
    LabelDetailWidget {
        border: solid $accent;
        height: 8;
        color: $text;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.label = None

    def render(self) -> str:
        """Render label details."""
        if not self.label:
            return "[dim]Select a label to view details[/dim]"
        color = self.label.get("color") or "-"
        count = self.label.get("issueCount") or "-"
        description = self.label.get("description") or "-"
        return (
            f"[bold cyan]{self.label.get('name', '?')}[/bold cyan]\n"
            f"[dim]Issue Count:[/dim] {count}\n"
            f"[dim]Color:[/dim] {color}\n"
            f"[dim]Description:[/dim] {description}"
        )

    def update_label(self, label: dict | None) -> None:
        """Update displayed label."""
        self.label = label
        self.update(self.render())
