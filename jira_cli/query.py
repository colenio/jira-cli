"""JQL query builder and search logic."""

from typing import Optional

from .client import JiraClient
from .models import IssueRow


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
        jql_extra: Optional[str] = None,
        fields: Optional[list[str]] = None,
        max_results: int = 50,
    ) -> list[IssueRow]:
        """
        Search issues in a project with optional filters.
        
        Args:
            project_key: Jira project key
            status: Filter by status (e.g. 'To Do', 'In Progress')
            assignee: Filter by assignee
            label: Filter by label
            jql_extra: Additional JQL conditions (AND appended)
            fields: Specific fields to fetch
            max_results: Max results to return
        
        Returns:
            List of IssueRow (flattened for output)
        """
        conditions = [f"project = {project_key}"]

        if status:
            conditions.append(f"status = '{status}'")
        if assignee:
            conditions.append(f"assignee = '{assignee}'")
        if label:
            conditions.append(f"labels = {label}")
        if jql_extra:
            conditions.append(jql_extra)

        jql = " AND ".join(conditions)

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
        Search issues by summary/description text.
        
        Args:
            project_key: Project key
            text: Search text
            fields: Specific fields to fetch
            max_results: Max results
        
        Returns:
            List of IssueRow
        """
        jql = f'project = {project_key} AND (summary ~ "{text}" OR description ~ "{text}")'
        return self.search_custom_jql(jql, fields=fields, max_results=max_results)
