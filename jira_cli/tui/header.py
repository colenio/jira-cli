"""Top bar showing app title, current Jira user, and clock."""

from datetime import datetime

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.events import Mount
from textual.widgets import Static


class JiraTopBar(Horizontal):
    """Single-row top bar with explicit columns, avoiding Header dock overlap."""

    DEFAULT_CSS = """
    JiraTopBar {
        dock: top;
        width: 100%;
        height: 1;
        background: $panel;
        color: $foreground;
    }

    JiraTopBar #topbar_title {
        width: 1fr;
        padding: 0 1;
        content-align: left middle;
        text-wrap: nowrap;
        text-overflow: ellipsis;
    }

    JiraTopBar #topbar_user {
        width: auto;
        padding: 0 1;
        content-align: right middle;
        text-opacity: 85%;
        text-wrap: nowrap;
    }

    JiraTopBar #topbar_clock {
        width: 10;
        padding: 0 1;
        background: $foreground-darken-1 5%;
        content-align: center middle;
        text-opacity: 85%;
    }
    """

    def __init__(self, user_display_name: str = "", title: str = "Jira CLI", **kwargs):
        super().__init__(**kwargs)
        self.user_display_name = user_display_name
        self.bar_title = title

    def compose(self) -> ComposeResult:
        yield Static(self.bar_title, id="topbar_title")
        if self.user_display_name:
            yield Static(self.user_display_name, id="topbar_user")
        yield Static(self._time_text(), id="topbar_clock")

    def on_mount(self, _: Mount) -> None:
        self.set_interval(1, self._update_clock, name="update topbar clock")

    def _update_clock(self) -> None:
        self.query_one("#topbar_clock", Static).update(self._time_text())

    @staticmethod
    def _time_text() -> str:
        return datetime.now().time().strftime("%X")
