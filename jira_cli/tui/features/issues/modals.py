"""Modal forms for editing issues and writing comments."""

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, TextArea


class EditIssueModal(ModalScreen[dict | None]):
    """Edit common issue fields in one compact form."""

    DEFAULT_CSS = """
    EditIssueModal {
        align: center middle;
    }
    #edit_issue_modal {
        width: 80;
        height: auto;
        max-height: 90%;
        padding: 1 2;
        border: round $accent;
        background: $surface;
    }
    #edit_issue_modal TextArea {
        height: 8;
        margin: 1 0;
    }
    #edit_issue_modal Input {
        margin: 1 0;
    }
    #edit_issue_buttons {
        height: auto;
        align: right middle;
    }
    #edit_issue_buttons Button {
        margin-left: 1;
    }
    """

    def __init__(self, issue_key: str, title: str, description: str = "", labels: str = ""):
        super().__init__()
        self.issue_key = issue_key
        self.initial_title = title
        self.initial_description = description
        self.initial_labels = labels

    def compose(self) -> ComposeResult:
        with Vertical(id="edit_issue_modal"):
            yield Label(f"Edit {self.issue_key}", classes="modal-title")
            yield Input(value=self.initial_title, placeholder="Title", id="edit_title")
            yield TextArea(self.initial_description, placeholder="Description", id="edit_description")
            yield Input(value=self.initial_labels, placeholder="Labels (comma-separated)", id="edit_labels")
            with Horizontal(id="edit_issue_buttons"):
                yield Button("Cancel", id="edit_cancel")
                yield Button("Save", variant="primary", id="edit_save")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "edit_cancel":
            self.dismiss(None)
            return
        if event.button.id == "edit_save":
            self.dismiss(
                {
                    "summary": self.query_one("#edit_title", Input).value.strip(),
                    "description": self.query_one("#edit_description", TextArea).text,
                    "labels": [label.strip() for label in self.query_one("#edit_labels", Input).value.split(",") if label.strip()],
                }
            )

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(None)
            event.prevent_default()
            event.stop()


class CommentModal(ModalScreen[str | None]):
    """Read the current thread and compose a multiline comment."""

    DEFAULT_CSS = """
    CommentModal {
        align: center middle;
    }
    #comment_modal {
        width: 90;
        height: 85%;
        padding: 1 2;
        border: round $accent;
        background: $surface;
    }
    #comment_thread {
        height: 1fr;
        overflow-y: auto;
        border: solid $panel;
        padding: 1;
    }
    #comment_editor {
        height: 8;
        margin: 1 0;
    }
    #comment_buttons {
        height: auto;
        align: right middle;
    }
    #comment_buttons Button {
        margin-left: 1;
    }
    """

    def __init__(self, issue_key: str, thread: str):
        super().__init__()
        self.issue_key = issue_key
        self.thread = thread

    def compose(self) -> ComposeResult:
        with Vertical(id="comment_modal"):
            yield Label(f"Comments for {self.issue_key}", classes="modal-title")
            yield Label(self.thread or "No comments yet", id="comment_thread")
            yield TextArea(placeholder="Write a comment...", id="comment_editor")
            with Horizontal(id="comment_buttons"):
                yield Button("Cancel", id="comment_cancel")
                yield Button("Send", variant="primary", id="comment_send")

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(None)
            event.prevent_default()
            event.stop()
            return
        if event.key == "ctrl+enter":
            self._send()
            event.prevent_default()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "comment_cancel":
            self.dismiss(None)
        elif event.button.id == "comment_send":
            self._send()

    def _send(self) -> None:
        text = self.query_one("#comment_editor", TextArea).text
        self.dismiss(text if text.strip() else None)
