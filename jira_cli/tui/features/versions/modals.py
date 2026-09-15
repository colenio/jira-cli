"""Modal form for version and milestone management."""

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, Input, Label, TextArea


class VersionModal(ModalScreen[dict | None]):
    """Create, edit, release, or delete a version/milestone."""

    DEFAULT_CSS = """
    VersionModal { align: center middle; }
    #version_modal {
        width: 72;
        height: auto;
        padding: 1 2;
        border: round $accent;
        background: $surface;
    }
    #version_modal Input { margin: 1 0; }
    #version_description { height: 6; margin: 1 0; }
    #version_buttons { height: auto; align: right middle; }
    #version_buttons Button { margin-left: 1; }
    """

    def __init__(self, version: dict | None = None):
        super().__init__()
        self.version = version

    def compose(self) -> ComposeResult:
        current = self.version or {}
        with Vertical(id="version_modal"):
            yield Label("Edit version / milestone" if self.version else "Create version / milestone")
            yield Input(value=current.get("name", ""), placeholder="Name", id="version_name")
            yield TextArea(current.get("description", "") or "", placeholder="Description", id="version_description")
            yield Input(value=current.get("releaseDate", "") or "", placeholder="Release date (YYYY-MM-DD)", id="version_date")
            yield Checkbox("Released / closed", value=bool(current.get("released")), id="version_released")
            with Horizontal(id="version_buttons"):
                if self.version:
                    yield Button("Delete", variant="error", id="version_delete")
                yield Button("Cancel", id="version_cancel")
                yield Button("Save", variant="primary", id="version_save")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "version_cancel":
            self.dismiss(None)
        elif event.button.id == "version_delete":
            self.dismiss({"action": "delete", "name": self.version.get("name", "")})
        elif event.button.id == "version_save":
            self.dismiss({
                "action": "edit" if self.version else "create",
                "original_name": (self.version or {}).get("name", ""),
                "id": (self.version or {}).get("id", ""),
                "name": self.query_one("#version_name", Input).value.strip(),
                "description": self.query_one("#version_description", TextArea).text,
                "releaseDate": self.query_one("#version_date", Input).value.strip(),
                "released": self.query_one("#version_released", Checkbox).value,
            })

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(None)
            event.prevent_default()
            event.stop()
