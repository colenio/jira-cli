"""User table/detail widgets for the Jira TUI."""

from textual.widgets import DataTable, Static


class UserTableWidget(DataTable):
    """Interactive table displaying Jira users."""

    def __init__(self, users: list[dict], **kwargs):
        super().__init__(**kwargs)
        self.users = users

    def on_mount(self) -> None:
        """Configure the table on mount."""
        self.add_columns("Display Name", "Email", "Active")
        self.cursor_type = "row"
        self._add_rows(self.users)

    def _add_rows(self, users: list[dict]) -> None:
        for user in users:
            active = "yes" if user.get("active", True) else "no"
            self.add_row(
                user.get("displayName", "?"),
                user.get("emailAddress", "-"),
                active,
                key=user.get("accountId") or user.get("displayName", ""),
            )

    def replace_rows(self, users: list[dict], preferred_key: str | None = None) -> dict | None:
        """Replace table rows and keep selection if possible."""
        self.users = users
        self.clear()
        self._add_rows(users)

        if not users:
            return None

        selected_index = 0
        if preferred_key:
            for index, user in enumerate(users):
                if (user.get("accountId") or user.get("displayName", "")) == preferred_key:
                    selected_index = index
                    break

        try:
            self.move_cursor(row=selected_index, column=0)
        except Exception:
            pass

        return users[selected_index]

    def get_selected_user(self) -> dict | None:
        """Get the currently selected user."""
        if self.cursor_row >= 0 and self.cursor_row < len(self.users):
            return self.users[self.cursor_row]
        return None


class UserDetailWidget(Static):
    """Display details for the selected Jira user."""

    DEFAULT_CSS = """
    UserDetailWidget {
        border: solid $accent;
        height: 8;
        color: $text;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.user = None

    def render(self) -> str:
        """Render user details."""
        if not self.user:
            return "[dim]Select a user to view details[/dim]"
        return (
            f"[bold cyan]{self.user.get('displayName', '?')}[/bold cyan]\n"
            f"[dim]Email:[/dim] {self.user.get('emailAddress', '-')}\n"
            f"[dim]Account ID:[/dim] {self.user.get('accountId', '-')}\n"
            f"[dim]Active:[/dim] {'yes' if self.user.get('active', True) else 'no'}"
        )

    def update_user(self, user: dict | None) -> None:
        """Update displayed user."""
        self.user = user
        self.update(self.render())
