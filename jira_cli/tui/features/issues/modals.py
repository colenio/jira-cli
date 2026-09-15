"""Modal forms for editing issues and writing comments."""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Markdown, SelectionList, TextArea


class CommentThreadMarkdown(Markdown):
    """Focusable, keyboard-scrollable Markdown comment thread."""

    can_focus = True
    BINDINGS = [
        Binding("up,k", "scroll_up", "Scroll up", show=False),
        Binding("down,j", "scroll_down", "Scroll down", show=False),
        Binding("pageup", "page_up", "Page up", show=False),
        Binding("pagedown", "page_down", "Page down", show=False),
        Binding("home", "scroll_home", "First comment", show=False),
        Binding("end", "scroll_end", "Last comment", show=False),
    ]

    def action_scroll_up(self) -> None:
        self.scroll_up()

    def action_scroll_down(self) -> None:
        self.scroll_down()

    def action_page_up(self) -> None:
        self.scroll_page_up()

    def action_page_down(self) -> None:
        self.scroll_page_down()

    def action_scroll_home(self) -> None:
        self.scroll_home()

    def action_scroll_end(self) -> None:
        self.scroll_end()


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
    #edit_labels {
        height: 8;
        border: solid $panel;
    }
    #edit_issue_buttons {
        height: auto;
        align: right middle;
    }
    #edit_issue_buttons Button {
        margin-left: 1;
    }
    """

    def __init__(
        self,
        issue_key: str,
        title: str,
        description: str = "",
        labels: str = "",
        label_candidates: list[str] | None = None,
    ):
        super().__init__()
        self.issue_key = issue_key
        self.initial_title = title
        self.initial_description = description
        self.initial_labels = labels
        self.label_candidates = label_candidates or []
        self.selected_labels = {label.strip() for label in labels.split(",") if label.strip()}

    def compose(self) -> ComposeResult:
        with Vertical(id="edit_issue_modal"):
            yield Label(f"Edit {self.issue_key}", classes="modal-title")
            yield Input(value=self.initial_title, placeholder="Title", id="edit_title")
            yield TextArea(self.initial_description, placeholder="Description", id="edit_description")
            yield Input(placeholder="Filter labels", id="label_filter")
            yield SelectionList(*self._label_options(), id="edit_labels")
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
                    "labels": sorted(self.selected_labels),
                }
            )

    def on_input_changed(self, event: Input.Changed) -> None:
        """Filter available labels without losing the current selection."""
        if event.input.id != "label_filter":
            return
        label_list = self.query_one("#edit_labels", SelectionList)
        label_list.set_options(self._label_options(event.value))

    def on_selection_list_selected_changed(self, event: SelectionList.SelectedChanged) -> None:
        if event.selection_list.id != "edit_labels":
            return
        visible = {option.value for option in event.selection_list.options}
        self.selected_labels.difference_update(visible)
        self.selected_labels.update(event.selection_list.selected)

    def _label_options(self, query: str = "") -> list[tuple[str, str, bool]]:
        """Return filtered label options with their current selected state."""
        all_labels = list(dict.fromkeys([*self.label_candidates, *self.selected_labels]))
        query_lower = query.strip().casefold()
        return [
            (label, label, label in self.selected_labels)
            for label in sorted(all_labels, key=str.casefold)
            if not query_lower or query_lower in label.casefold()
        ]

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
    #mention_suggestion {
        height: 1;
        color: $text-muted;
    }
    #comment_buttons {
        height: auto;
        align: right middle;
    }
    #comment_buttons Button {
        margin-left: 1;
    }
    """

    def __init__(self, issue_key: str, thread: str, mention_users: list[dict] | None = None):
        super().__init__()
        self.issue_key = issue_key
        self.thread = thread
        self.mention_users = mention_users or []
        self._mention_replacement: tuple[tuple[int, int], tuple[int, int], str] | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="comment_modal"):
            yield Label(f"Comments for {self.issue_key}", classes="modal-title")
            yield CommentThreadMarkdown(self.thread or "No comments yet", id="comment_thread", open_links=False)
            yield TextArea(placeholder="Write a comment...", id="comment_editor")
            yield Label("", id="mention_suggestion")
            with Horizontal(id="comment_buttons"):
                yield Button("Cancel", id="comment_cancel")
                yield Button("Send", variant="primary", id="comment_send")

    def on_mount(self) -> None:
        """Start on the thread so existing comments are immediately keyboard-scrollable."""
        self.query_one("#comment_thread", CommentThreadMarkdown).focus()

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(None)
            event.prevent_default()
            event.stop()
            return
        if event.key == "ctrl+enter":
            self._send()
            event.prevent_default()
            return
        if event.key == "tab" and self._mention_replacement and self.focused.id == "comment_editor":
            start, end, replacement = self._mention_replacement
            editor = self.query_one("#comment_editor", TextArea)
            editor.replace(replacement, start, end)
            self._clear_mention_suggestion()
            event.prevent_default()
            event.stop()
            return

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "comment_cancel":
            self.dismiss(None)
        elif event.button.id == "comment_send":
            self._send()

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        if event.text_area.id != "comment_editor":
            return
        editor = event.text_area
        row, column = editor.cursor_location
        lines = editor.text.splitlines() or [""]
        line = lines[row] if row < len(lines) else ""
        prefix = line[:column]
        token_start = prefix.rfind("@")
        if token_start < 0:
            self._clear_mention_suggestion()
            return
        token = prefix[token_start + 1 :]
        if not token or any(char.isspace() for char in token):
            self._clear_mention_suggestion()
            return

        token_lower = token.casefold()
        for user in self.mention_users:
            account_id = str(user.get("accountId", "")).lstrip("@")
            display_name = str(user.get("displayName", ""))
            if not account_id:
                continue
            if account_id.casefold().startswith(token_lower) or display_name.casefold().startswith(token_lower):
                self._mention_replacement = ((row, token_start), (row, column), f"@{account_id}")
                self.query_one("#mention_suggestion", Label).update(
                    f"Tab: {display_name or account_id} (@{account_id})"
                )
                return
        self._clear_mention_suggestion()

    def _clear_mention_suggestion(self) -> None:
        self._mention_replacement = None
        self.query_one("#mention_suggestion", Label).update("")

    def _send(self) -> None:
        text = self.query_one("#comment_editor", TextArea).text
        self.dismiss(text if text.strip() else None)
