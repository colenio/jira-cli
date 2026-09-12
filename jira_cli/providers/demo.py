"""Demo provider implementation."""

from __future__ import annotations

from jira_cli.demo import DemoJiraClient

from .base import ActionDescriptor, FilterDescriptor, ProviderDescriptor, ResourceDescriptor, SortDescriptor

DEMO_PROVIDER_DESCRIPTOR = ProviderDescriptor(
    name="demo",
    resources=(
        ResourceDescriptor(
            kind="issues",
            fields=("key", "summary", "type", "status", "assignee", "priority", "labels", "updated", "parent"),
            filters=(
                FilterDescriptor("type", "issuetype"),
                FilterDescriptor("status", "status"),
                FilterDescriptor("assignee", "assignee", special_values=("me",)),
                FilterDescriptor("label", "labels"),
                FilterDescriptor("priority", "priority"),
                FilterDescriptor("key", "key"),
            ),
            sorts=(
                SortDescriptor("key", "key"),
                SortDescriptor("priority", "priority"),
                SortDescriptor("updated", "updated", default_direction="desc"),
                SortDescriptor("status", "status"),
            ),
            actions=(
                ActionDescriptor("comment"),
                ActionDescriptor("assign"),
                ActionDescriptor("transition"),
            ),
        ),
        ResourceDescriptor(
            kind="users",
            fields=("displayName", "emailAddress", "active", "accountId"),
            filters=(FilterDescriptor("query", "query"),),
        ),
        ResourceDescriptor(
            kind="versions",
            fields=("name", "description", "releaseDate", "released", "archived"),
        ),
    ),
)


class DemoProvider(DemoJiraClient):
    """Synthetic provider for screenshots, demos, and provider-contract tests."""

    def describe(self) -> ProviderDescriptor:
        """Describe demo resources and capabilities."""
        return DEMO_PROVIDER_DESCRIPTOR
