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
