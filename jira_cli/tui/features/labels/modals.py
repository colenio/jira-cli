"""Modal form for GitHub repository label management."""

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label


class LabelModal(ModalScreen[dict | None]):
    """Create, edit, or delete one repository label."""

    DEFAULT_CSS = """
    LabelModal { align: center middle; }
    #label_modal {
        width: 70;
        height: auto;
        padding: 1 2;
        border: round $accent;
        background: $surface;
    }
    #label_modal Input { margin: 1 0; }
    #label_buttons { height: auto; align: right middle; }
    #label_buttons Button { margin-left: 1; }
    """

    def __init__(self, label: dict | None = None):
        super().__init__()
        self.label = label

    def compose(self) -> ComposeResult:
        current = self.label or {}
        with Vertical(id="label_modal"):
            yield Label("Edit label" if self.label else "Create label")
            yield Input(value=current.get("name", ""), placeholder="Name", id="label_name")
            yield Input(value=current.get("color", "") or "ededed", placeholder="Color (hex, without #)", id="label_color")
            yield Input(value=current.get("description", "") or "", placeholder="Description", id="label_description")
            with Horizontal(id="label_buttons"):
                if self.label:
                    yield Button("Delete", variant="error", id="label_delete")
                yield Button("Cancel", id="label_cancel")
                yield Button("Save", variant="primary", id="label_save")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "label_cancel":
            self.dismiss(None)
        elif event.button.id == "label_delete":
            self.dismiss({"action": "delete", "name": self.label.get("name", "")})
        elif event.button.id == "label_save":
            self.dismiss({
                "action": "edit" if self.label else "create",
                "original_name": (self.label or {}).get("name", ""),
                "name": self.query_one("#label_name", Input).value.strip(),
                "color": self.query_one("#label_color", Input).value.strip().lstrip("#"),
                "description": self.query_one("#label_description", Input).value.strip(),
            })

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(None)
            event.prevent_default()
            event.stop()
