"""Version table/detail widgets for the Jira TUI."""

from textual.widgets import DataTable, Static


class VersionTableWidget(DataTable):
    """Interactive table displaying Jira fix versions/milestones."""

    def __init__(self, versions: list[dict], **kwargs):
        super().__init__(**kwargs)
        self.versions = versions

    def on_mount(self) -> None:
        """Configure the table on mount."""
        self.add_columns("Name", "Status", "Release Date")
        self.cursor_type = "row"
        self._add_rows(self.versions)

    def _add_rows(self, versions: list[dict]) -> None:
        for version in versions:
            state = "released" if version.get("released") else "unreleased"
            if version.get("archived"):
                state = f"{state}, archived"
            self.add_row(
                version.get("name", "?"),
                state,
                version.get("releaseDate", "-"),
                key=version.get("id") or version.get("name", ""),
            )

    def replace_rows(self, versions: list[dict], preferred_key: str | None = None) -> dict | None:
        """Replace table rows and keep selection if possible."""
        self.versions = versions
        self.clear()
        self._add_rows(versions)

        if not versions:
            return None

        selected_index = 0
        if preferred_key:
            for index, version in enumerate(versions):
                if (version.get("id") or version.get("name", "")) == preferred_key:
                    selected_index = index
                    break

        try:
            self.move_cursor(row=selected_index, column=0)
        except Exception:
            pass

        return versions[selected_index]

    def get_selected_version(self) -> dict | None:
        """Get the currently selected version."""
        if self.cursor_row >= 0 and self.cursor_row < len(self.versions):
            return self.versions[self.cursor_row]
        return None


class VersionDetailWidget(Static):
    """Display details for the selected Jira version/milestone."""

    DEFAULT_CSS = """
    VersionDetailWidget {
        border: solid $accent;
        height: 8;
        color: $text;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.version = None

    def render(self) -> str:
        """Render version details."""
        if not self.version:
            return "[dim]Select a version to view details[/dim]"
        released = "yes" if self.version.get("released") else "no"
        archived = "yes" if self.version.get("archived") else "no"
        return (
            f"[bold cyan]{self.version.get('name', '?')}[/bold cyan]\n"
            f"[dim]Description:[/dim] {self.version.get('description') or '-'}\n"
            f"[dim]Release Date:[/dim] {self.version.get('releaseDate', '-')}\n"
            f"[dim]Released:[/dim] {released} | [dim]Archived:[/dim] {archived}"
        )

    def update_version(self, version: dict | None) -> None:
        """Update displayed version."""
        self.version = version
        self.update(self.render())
