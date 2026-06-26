"""Query feature services for Jira TUI."""

from typing import Literal

from jira_cli.models import IssueRow
from jira_cli.query import JiraQuery

QueryMode = Literal["project", "find", "jql"]


def build_query_labels(project_key: str, query_mode: QueryMode, query_expression: str) -> tuple[str, str]:
    """Build mode and source labels for the current query state."""
    mode_label = f"MODE: {query_mode.upper()}"

    if query_mode == "project":
        return mode_label, f"Source: project={project_key}"
    if query_mode == "find":
        return mode_label, f"Source: find \"{query_expression}\""

    snippet = query_expression.strip().replace("\n", " ")
    if len(snippet) > 80:
        snippet = f"{snippet[:77]}..."
    return mode_label, f"Source: jql {snippet}"


def run_remote_query(
    query: JiraQuery,
    project_key: str,
    query_mode: QueryMode,
    query_expression: str,
    max_results: int = 100,
) -> list[IssueRow]:
    """Run query for active mode and return flattened rows."""
    if query_mode == "find":
        return query.find_by_text(project_key, query_expression, max_results=max_results)
    if query_mode == "jql":
        return query.search_custom_jql(query_expression, max_results=max_results)
    return query.search_project(project_key=project_key, max_results=max_results)


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
