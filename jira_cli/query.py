"""JQL query builder and search logic."""

import re
from typing import Optional

from .client import JiraClient
from .models import IssueRow
from .quick_filters import QuickFilterResolver

_ISSUE_KEY_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9]*-\d+$")

ORDER_FIELDS = {
    "assignee": "assignee",
    "created": "created",
    "due": "duedate",
    "duedate": "duedate",
    "key": "key",
    "priority": "priority",
    "rank": "Rank",
    "status": "status",
    "type": "issuetype",
    "updated": "updated",
}
ORDER_DIRECTIONS = {"asc", "desc"}


def order_by_clause(order_by: str | None) -> str:
    """Build a whitelisted JQL ORDER BY clause from '<field> [asc|desc]'."""
    if not order_by:
        return ""

    parts = order_by.strip().replace(":", " ").split()
    if not parts:
        return ""
    if len(parts) > 2:
        raise ValueError("Order must be '<field>' or '<field> <asc|desc>'")

    field_key = parts[0].lower()
    field = ORDER_FIELDS.get(field_key)
    if not field:
        allowed = ", ".join(sorted(ORDER_FIELDS))
        raise ValueError(f"Unknown order field '{parts[0]}'. Use one of: {allowed}")

    direction = parts[1].lower() if len(parts) == 2 else "asc"
    if direction not in ORDER_DIRECTIONS:
        raise ValueError("Order direction must be 'asc' or 'desc'")

    return f"ORDER BY {field} {direction.upper()}"


class JiraQuery:
    """Build and execute JQL queries."""

    def __init__(self, client: JiraClient):
        self.client = client

    def search_project(
        self,
        project_key: str,
        status: Optional[str] = None,
        assignee: Optional[str] = None,
        label: Optional[str] = None,
        issue_type: Optional[str] = None,
        priority: Optional[str] = None,
        order_by: Optional[str] = None,
        jql_extra: Optional[str] = None,
        fields: Optional[list[str]] = None,
        max_results: int = 50,
    ) -> list[IssueRow]:
        """
        Search issues in a project with optional filters.
        
        Args:
            project_key: Jira project key
            status: Filter by status (e.g. 'To Do', 'In Progress')
            assignee: Filter by assignee (or 'me' for the authenticated account)
            label: Filter by label
            issue_type: Filter by issue type (e.g. 'Bug', 'Story')
            priority: Filter by priority (e.g. 'High')
            order_by: Sort by whitelisted JQL field, optionally with asc/desc
            jql_extra: Additional JQL conditions (AND appended)
            fields: Specific fields to fetch
            max_results: Max results to return
        
        Returns:
            List of IssueRow (flattened for output)
        """
        conditions = [f"project = {project_key}"]
        resolver = QuickFilterResolver(self.client, project_key)

        if status:
            conditions.append(resolver.clause("status", status))
        if assignee:
            _, clause = resolver.resolve("assignee", assignee)
            conditions.append(clause)
        if label:
            conditions.append(resolver.clause("label", label))
        if issue_type:
            conditions.append(resolver.clause("type", issue_type))
        if priority:
            conditions.append(resolver.clause("priority", priority))
        if jql_extra:
            conditions.append(jql_extra)

        jql = " AND ".join(conditions)
        order_clause = order_by_clause(order_by)
        if order_clause:
            jql = f"{jql} {order_clause}"

        # Default fields to fetch
        if not fields:
            fields = [
                "key",
                "summary",
                "issuetype",
                "parent",
                "subtasks",
                "status",
                "priority",
                "assignee",
                "updated",
                "labels",
            ]

        result = self.client.search(jql, fields=fields, max_results=max_results)

        return [IssueRow.from_jira_issue(issue) for issue in result.issues]

    def search_custom_jql(self, jql: str, fields: Optional[list[str]] = None, max_results: int = 50) -> list[IssueRow]:
        """
        Execute custom JQL query.
        
        Args:
            jql: Full JQL query string
            fields: Specific fields to fetch
            max_results: Max results
        
        Returns:
            List of IssueRow
        """
        if not fields:
            fields = [
                "key",
                "summary",
                "issuetype",
                "parent",
                "subtasks",
                "status",
                "priority",
                "assignee",
                "updated",
                "labels",
            ]

        result = self.client.search(jql, fields=fields, max_results=max_results)
        return [IssueRow.from_jira_issue(issue) for issue in result.issues]

    def find_by_text(
        self, project_key: str, text: str, fields: Optional[list[str]] = None, max_results: int = 50
    ) -> list[IssueRow]:
        """
        Search issues by summary/description text, or by exact issue key if `text` looks like one.

        Args:
            project_key: Project key
            text: Search text (or an issue key, e.g. 'PROJ-123')
            fields: Specific fields to fetch
            max_results: Max results

        Returns:
            List of IssueRow
        """
        text = text.strip()
        clauses = [f'summary ~ "{text}"', f'description ~ "{text}"']
        if _ISSUE_KEY_PATTERN.match(text):
            clauses.insert(0, f"key = {text.upper()}")
        jql = f"project = {project_key} AND ({' OR '.join(clauses)})"
        return self.search_custom_jql(jql, fields=fields, max_results=max_results)

    def find_children(self, key: str, fields: Optional[list[str]] = None, max_results: int = 50) -> list[IssueRow]:
        """
        Find child issues of `key` via Jira's 'parent' field.

        Covers Epic -> Story/Task and Story -> Sub-task alike, since modern Jira Cloud
        hierarchy uses 'parent' uniformly (an issue's own 'subtasks' field only reflects
        actual sub-tasks, never an Epic's Story/Task children).

        Args:
            key: Parent issue key (e.g. an Epic or Story)
            fields: Specific fields to fetch
            max_results: Max results

        Returns:
            List of IssueRow
        """
        return self.search_custom_jql(self.children_jql(key), fields=fields, max_results=max_results)

    @staticmethod
    def children_jql(key: str) -> str:
        """JQL for an issue's children via Jira's 'parent' field (shared by CLI and TUI)."""
        return f"parent = {key} ORDER BY key"

    def find_overdue(
        self, project_key: str, mine: bool = False, fields: Optional[list[str]] = None, max_results: int = 50
    ) -> list[IssueRow]:
        """
        Find overdue issues: due date passed, not in a Done-category status.

        Args:
            project_key: Project key
            mine: If True, restrict to issues assigned to the authenticated account
            fields: Specific fields to fetch
            max_results: Max results

        Returns:
            List of IssueRow
        """
        return self.search_custom_jql(self.overdue_jql(project_key, mine=mine), fields=fields, max_results=max_results)

    @staticmethod
    def overdue_jql(project_key: str, mine: bool = False) -> str:
        """JQL for overdue issues (shared by CLI and TUI)."""
        clauses = [f"project = {project_key}", "duedate < now()", "statusCategory != Done"]
        if mine:
            clauses.append("assignee = currentUser()")
        return " AND ".join(clauses) + " ORDER BY duedate ASC"
