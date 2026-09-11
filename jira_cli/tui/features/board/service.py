"""Pure helpers for grouping issues into board (status) columns."""

from jira_cli.models import IssueRow

# Common workflow order; unmapped in-flight statuses are inserted before terminal states.
DEFAULT_STATUS_ORDER = [
    "Backlog",
    "To Do",
    "Open",
    "Selected for Development",
    "In Progress",
    "In Review",
    "Blocked",
    "Done",
    "Closed",
]
TERMINAL_STATUS_ORDER = ["Done", "Closed", "Resolved"]

NO_STATUS_LABEL = "No Status"


def group_by_status(
    issues: list[IssueRow], status_order: list[str] | None = None
) -> dict[str, list[IssueRow]]:
    """Group issues into ordered status columns (known order first, rest alphabetical)."""
    order = status_order if status_order is not None else DEFAULT_STATUS_ORDER

    buckets: dict[str, list[IssueRow]] = {}
    for issue in issues:
        status = issue.status or NO_STATUS_LABEL
        buckets.setdefault(status, []).append(issue)

    terminal = [status for status in TERMINAL_STATUS_ORDER if status in buckets]
    terminal_set = set(terminal)
    known = [status for status in order if status in buckets and status not in terminal_set]
    rest = sorted(status for status in buckets if status not in order and status not in terminal_set)

    return {status: buckets[status] for status in [*known, *rest, *terminal]}
