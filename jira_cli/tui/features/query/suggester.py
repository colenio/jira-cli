"""Dynamic ':' command-bar suggester for the Jira TUI (k9s/sofka-style palette)."""

from typing import Callable

from textual.suggester import Suggester

from jira_cli.models import IssueRow

from jira_cli.query import ORDER_FIELDS

from .service import QUICK_FILTER_DIMENSIONS

_VERBS = [
    "table",
    "board",
    "issues",
    "view",
    "open",
    "clear",
    "next",
    "me",
    "users",
    "user=",
    "labels",
    "versions",
    "milestones",
    "overdue",
    "overdue=me",
    "order=",
    *(f"{verb}=" for verb in QUICK_FILTER_DIMENSIONS),
]


class CommandSuggester(Suggester):
    """Suggests verbs (table/board/clear/type/status/assignee/label) and their values."""

    def __init__(
        self,
        issues_provider: Callable[[], list[IssueRow]],
        assignees_provider: Callable[[], list[str]] | None = None,
        verbs_provider: Callable[[], list[str]] | None = None,
    ):
        super().__init__(use_cache=False, case_sensitive=False)
        self._issues_provider = issues_provider
        self._assignees_provider = assignees_provider
        self._verbs_provider = verbs_provider

    async def get_suggestion(self, value: str) -> str | None:
        if value.lower().startswith("order="):
            arg = value[len("order="):]
            match = self._first_prefix_match(sorted(ORDER_FIELDS), arg)
            return f"order={match}" if match else None

        for verb, (distinct_fn, _attr) in QUICK_FILTER_DIMENSIONS.items():
            prefix = f"{verb}="
            if value.lower().startswith(prefix):
                arg = value[len(prefix):]
                candidates = distinct_fn(self._issues_provider())
                if verb == "assignee":
                    external = self._assignees_provider() if self._assignees_provider else []
                    candidates = ["me", "none", "unassigned", *sorted(set(candidates) | set(external))]
                match = self._first_prefix_match(candidates, arg)
                return f"{prefix}{match}" if match else None

        verbs = self._verbs_provider() if self._verbs_provider else _VERBS
        return self._first_prefix_match(verbs, value)

    @staticmethod
    def _first_prefix_match(candidates: list[str], value: str) -> str | None:
        value_lower = value.lower()
        if not value_lower:
            return None
        for candidate in candidates:
            if candidate.lower().startswith(value_lower) and candidate.lower() != value_lower:
                return candidate
        return None
