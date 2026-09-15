"""Modal choices for user resource actions."""

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label


class UserIssuesModal(ModalScreen[str | None]):
    """Choose whether to show issues assigned to or reported by a user."""

    DEFAULT_CSS = """
    UserIssuesModal { align: center middle; }
    #user_issues_modal {
        width: 60;
        height: auto;
        padding: 1 2;
        border: round $accent;
        background: $surface;
    }
    #user_issues_buttons { height: auto; align: center middle; }
    #user_issues_buttons Button { margin: 1; }
    """

    def __init__(self, display_name: str):
        super().__init__()
        self.display_name = display_name

    def compose(self) -> ComposeResult:
        with Vertical(id="user_issues_modal"):
            yield Label(f"Show issues for {self.display_name}")
            with Horizontal(id="user_issues_buttons"):
                yield Button("Assigned", variant="primary", id="user_assignee")
                yield Button("Reported", id="user_reporter")
                yield Button("Cancel", id="user_cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        choices = {"user_assignee": "assignee", "user_reporter": "reporter"}
        self.dismiss(choices.get(event.button.id))

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(None)
            event.prevent_default()
            event.stop()
