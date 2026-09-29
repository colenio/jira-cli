"""Demo provider implementation."""

from __future__ import annotations

from jira_cli.demo import DemoJiraClient

from .base import ActionDescriptor, FilterDescriptor, ProviderDescriptor, ResourceDescriptor, SortDescriptor

DEMO_PROVIDER_DESCRIPTOR = ProviderDescriptor(
    name="demo",
    query_language="demo query",
    resources=(
        ResourceDescriptor(
            kind="issues",
            fields=("key", "summary", "type", "status", "assignee", "priority", "labels", "updated", "parent"),
            filters=(
                FilterDescriptor(name="type", field="issuetype"),
                FilterDescriptor(name="status", field="status"),
                FilterDescriptor(name="assignee", field="assignee", special_values=("me",)),
                FilterDescriptor(name="label", field="labels"),
                FilterDescriptor(name="priority", field="priority"),
                FilterDescriptor(name="key", field="key"),
            ),
            sorts=(
                SortDescriptor(name="key", field="key"),
                SortDescriptor(name="priority", field="priority"),
                SortDescriptor(name="updated", field="updated", default_direction="desc"),
                SortDescriptor(name="status", field="status"),
            ),
            actions=(
                ActionDescriptor(name="create"),
                ActionDescriptor(name="edit"),
                ActionDescriptor(name="comment"),
                ActionDescriptor(name="assign"),
                ActionDescriptor(name="transition"),
            ),
        ),
        ResourceDescriptor(
            kind="users",
            fields=("displayName", "emailAddress", "active", "accountId"),
            filters=(FilterDescriptor(name="query", field="query"),),
        ),
        ResourceDescriptor(
            kind="versions",
            fields=("name", "description", "releaseDate", "released", "archived"),
            actions=(
                ActionDescriptor(name="create"),
                ActionDescriptor(name="edit"),
                ActionDescriptor(name="delete"),
                ActionDescriptor(name="release"),
            ),
        ),
        ResourceDescriptor(
            kind="labels",
            fields=("name", "color", "description", "issueCount"),
            actions=(
                ActionDescriptor(name="create"),
                ActionDescriptor(name="edit"),
                ActionDescriptor(name="delete"),
            ),
        ),
    ),
)


class DemoProvider(DemoJiraClient):
    """Synthetic provider for screenshots, demos, and provider-contract tests."""

    def get_issue_url(self, key: str) -> str:
        """Return the web URL for an issue key."""
        return f"https://example.atlassian.net/browse/{key}"

    def describe(self) -> ProviderDescriptor:
        """Describe demo resources and capabilities."""
        return DEMO_PROVIDER_DESCRIPTOR

    def list_resource(self, kind: str, project_key: str) -> list[dict]:
        """Return demo catalog resources when implemented."""
        raise ValueError(f"Demo provider does not expose resource '{kind}'")

    def list_timeline_items(self, project_key: str):
        """Return dated demo Epics as provider-neutral planning items."""
        from datetime import date

        from jira_cli.models import IssueRow
        from jira_cli.timeline import TimelineItem

        result = self.search(f"project = {project_key} AND issuetype = Epic ORDER BY key", max_results=100)
        items = []
        for issue in result.issues:
            row = IssueRow.from_jira_issue(issue)
            try:
                start = date.fromisoformat(row.start_date[:10]) if row.start_date else None
            except ValueError:
                start = None
            try:
                end = date.fromisoformat(row.due_date[:10]) if row.due_date else None
            except ValueError:
                end = None
            items.append(TimelineItem(row.key, row.summary, start, end, row.status, issue_type="Epic", target_url=self.get_issue_url(row.key)))
        return items
