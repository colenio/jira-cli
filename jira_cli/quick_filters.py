"""Shared quick-filter resolution logic used identically by the CLI and the TUI.

Living outside jira_cli/tui/ means CLI commands (e.g. `issue list --assignee`) and the
TUI's ':' command bar resolve values (typo/umlaut tolerance, the 'me' shortcut, JQL
clause building) exactly the same way, instead of duplicating this logic per surface.
"""

import unicodedata

from .providers import IssueTrackerProvider

_GERMAN_TRANSLITERATIONS = {"ß": "ss", "ä": "ae", "ö": "oe", "ü": "ue"}

# JQL field name for each quick-filter dimension.
QUICK_FILTER_JQL_FIELDS = {
    "type": "issuetype",
    "status": "status",
    "assignee": "assignee",
    "label": "labels",
    "priority": "priority",
    "key": "key",
}


def normalize_for_match(text: str) -> str:
    """Casefold + transliterate German umlauts + strip other diacritics, for typo-tolerant matching."""
    lowered = text.casefold()
    for umlaut, ascii_form in _GERMAN_TRANSLITERATIONS.items():
        lowered = lowered.replace(umlaut, ascii_form)
    decomposed = unicodedata.normalize("NFKD", lowered)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def resolve_value(candidates: list[str], value: str) -> str | None:
    """Resolve free-typed text to a known value: exact match first, then substring.

    Matching is umlaut/diacritic-tolerant (e.g. 'koertgen' matches 'Körtgen').
    """
    normalized_value = normalize_for_match(value.strip())
    if not normalized_value:
        return None
    for candidate in candidates:
        if normalize_for_match(candidate) == normalized_value:
            return candidate
    for candidate in candidates:
        if normalized_value in normalize_for_match(candidate):
            return candidate
    return None


def jql_literal(value: str) -> str:
    """Quote a value for safe use as a JQL string literal."""
    return '"' + value.replace('"', '\\"') + '"'


class QuickFilterResolver:
    """Resolves and builds JQL clauses for quick filters (type/status/assignee/label/key).

    Bound to one client + project_key so both the CLI (`issue list --assignee`, etc.) and the
    TUI's ':' command bar resolve values (typo/umlaut tolerance, the 'me' shortcut, JQL clause
    building, the assignable-users server-side fallback) through the exact same logic —
    keeping both surfaces thin.
    """

    def __init__(self, client: IssueTrackerProvider, project_key: str):
        self.client = client
        self.project_key = project_key

    def clause(self, dimension: str, value: str) -> str:
        """Build a JQL clause for one quick-filter dimension (server-side, never local-only)."""
        if dimension == "assignee" and value.strip().lower() == "me":
            return "assignee = currentUser()"
        if dimension == "key":
            return f"key = {value.strip().upper()}"
        field = QUICK_FILTER_JQL_FIELDS[dimension]
        return f"{field} = {jql_literal(value)}"

    def resolve(self, dimension: str, value: str, known_values: list[str] | None = None) -> tuple[str, str]:
        """Resolve a quick-filter value to (display_value, jql_clause).

        Order: 'me' (assignee only) -> currentUser(); else try `known_values` (e.g. already-
        loaded issues, fast, no API call); for 'assignee', fall back to Jira's assignable-users
        search (server-side, not limited to already-loaded issues) when nothing local matches;
        else use the raw typed value as a literal.
        """
        if dimension == "assignee" and value.strip().lower() == "me":
            return "me", "assignee = currentUser()"

        resolved = resolve_value(known_values or [], value)
        if not resolved and dimension == "assignee":
            try:
                users = self.client.find_assignable_users(self.project_key, value.strip())
                candidates = [u["displayName"] for u in users if u.get("displayName")]
            except Exception:
                candidates = []
            resolved = resolve_value(candidates, value)

        display_value = resolved or value.strip()
        return display_value, self.clause(dimension, display_value)
