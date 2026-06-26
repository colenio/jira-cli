"""Theme and color definitions for Textual TUI."""


class JiraTheme:
    """Jira-inspired color scheme."""

    # Status colors
    STATUS_TODO = "bold yellow"
    STATUS_IN_PROGRESS = "bold blue"
    STATUS_DONE = "bold green"
    STATUS_BLOCKED = "bold red"

    # UI colors
    HEADER = "bold white on blue"
    FOOTER = "white on dark_gray"
    FOCUS = "bold white on dark_blue"
    HIGHLIGHT = "bold cyan"
    ERROR = "bold red"
    SUCCESS = "bold green"
    MUTED = "dark_gray"

    # Borders
    BORDER = "cyan"
    BORDER_FOCUS = "bold cyan"
