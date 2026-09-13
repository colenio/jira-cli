"""Query feature services for Jira TUI."""

from typing import Literal

from jira_cli.models import IssueRow
from jira_cli.query import JiraQuery
from jira_cli.quick_filters import resolve_value as resolve_quick_filter_value

QueryMode = Literal["project", "find", "jql"]


def build_query_labels(
    project_key: str, query_mode: QueryMode, query_expression: str, query_language: str = "JQL"
) -> tuple[str, str]:
    """Build mode and source labels for the current query state."""
    mode_label = f"MODE: {query_language.upper()}" if query_mode == "jql" else f"MODE: {query_mode.upper()}"

    if query_mode == "project":
        return mode_label, f"Source: project={project_key}"
    if query_mode == "find":
        return mode_label, f"Source: find \"{query_expression}\""

    snippet = query_expression.strip().replace("\n", " ")
    if len(snippet) > 80:
        snippet = f"{snippet[:77]}..."
    return mode_label, f"Source: {query_language.lower()} {snippet}"


def run_remote_query(
    query: JiraQuery,
    project_key: str,
    query_mode: QueryMode,
    query_expression: str,
    order_by: str = "",
    max_results: int = 100,
) -> list[IssueRow]:
    """Run query for active mode and return flattened rows."""
    if query_mode == "find":
        return query.find_by_text(project_key, query_expression, max_results=max_results)
    if query_mode == "jql":
        return query.search_custom_jql(query_expression, max_results=max_results)
    return query.search_project(project_key=project_key, order_by=order_by or None, max_results=max_results)


def filter_issues(all_issues: list[IssueRow], filter_text: str) -> list[IssueRow]:
    """Apply in-memory text filter to issue rows."""
    query_text = (filter_text or "").strip().lower()
    if not query_text:
        return all_issues

    return [
        issue
        for issue in all_issues
        if query_text in issue.key.lower()
        or query_text in issue.summary.lower()
        or query_text in (issue.status or "").lower()
        or query_text in (issue.assignee or "").lower()
        or query_text in (issue.priority or "").lower()
    ]


def distinct_issue_types(all_issues: list[IssueRow]) -> list[str]:
    """Return sorted distinct issue types present in the loaded rows."""
    return _distinct_values(all_issues, lambda issue: issue.issue_type)


def distinct_priorities(all_issues: list[IssueRow]) -> list[str]:
    """Return sorted distinct priorities present in the loaded rows."""
    return _distinct_values(all_issues, lambda issue: issue.priority)


def _distinct_values(all_issues: list[IssueRow], accessor) -> list[str]:
    """Return sorted distinct non-empty values extracted via accessor."""
    values = {accessor(issue) for issue in all_issues if accessor(issue)}
    return sorted(values)


def distinct_statuses(all_issues: list[IssueRow]) -> list[str]:
    """Return sorted distinct statuses present in the loaded rows."""
    return _distinct_values(all_issues, lambda issue: issue.status)


def distinct_assignees(all_issues: list[IssueRow]) -> list[str]:
    """Return sorted distinct assignees present in the loaded rows."""
    return _distinct_values(all_issues, lambda issue: issue.assignee)


def _issue_labels(issue: IssueRow) -> list[str]:
    """Split the comma-joined labels string back into individual labels."""
    return [label.strip() for label in (issue.labels or "").split(",") if label.strip()]


def distinct_labels(all_issues: list[IssueRow]) -> list[str]:
    """Return sorted distinct labels present in the loaded rows."""
    labels: set[str] = set()
    for issue in all_issues:
        labels.update(_issue_labels(issue))
    return sorted(labels)


def distinct_issue_keys(all_issues: list[IssueRow]) -> list[str]:
    """Return sorted distinct issue keys present in the loaded rows."""
    return _distinct_values(all_issues, lambda issue: issue.key)


# Quick-filter dimensions exposed through the ':' command bar, sofka/k9s-style.
# distinct_fn is used only to power autocompletion/typo-tolerant resolution from the
# currently loaded page; the actual filter is always executed server-side (JQL) so it
# is never limited to issues already loaded in memory.
QUICK_FILTER_DIMENSIONS: dict[str, tuple] = {
    "type": (distinct_issue_types, "type_filter"),
    "status": (distinct_statuses, "status_filter"),
    "assignee": (distinct_assignees, "assignee_filter"),
    "label": (distinct_labels, "label_filter"),
    "priority": (distinct_priorities, "priority_filter"),
    "key": (distinct_issue_keys, "key_filter"),
}


def parse_command(text: str) -> tuple[str, str]:
    """Split a ':' command into (verb, argument).

    Quick filters use 'key=value' syntax (e.g. 'type=Story'); bare verbs like
    'table'/'board'/'clear' take no argument.
    """
    stripped = text.strip()
    if not stripped:
        return "", ""
    if "=" in stripped:
        verb, _, arg = stripped.partition("=")
        return verb.strip().lower(), arg.strip()
    return stripped.lower(), ""


def resolve_bare_quick_filter(all_issues: list[IssueRow], value: str) -> tuple[str, str] | None:
    """Resolve a bare ':<value>' command across type/status/assignee/label, sofka-palette style."""
    for dimension, (distinct_fn, _attr) in QUICK_FILTER_DIMENSIONS.items():
        match = resolve_quick_filter_value(distinct_fn(all_issues), value)
        if match:
            return dimension, match
    return None
