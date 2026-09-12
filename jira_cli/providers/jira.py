"""Jira provider implementation."""

from __future__ import annotations

from jira_cli.client import JiraClient

from .base import ActionDescriptor, FilterDescriptor, ProviderDescriptor, ResourceDescriptor, SortDescriptor

JIRA_PROVIDER_DESCRIPTOR = ProviderDescriptor(
    name="jira",
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
                SortDescriptor("rank", "Rank"),
            ),
            actions=(
                ActionDescriptor("comment"),
                ActionDescriptor("assign"),
                ActionDescriptor("transition"),
                ActionDescriptor("close"),
                ActionDescriptor("reopen"),
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
            actions=(ActionDescriptor("create"), ActionDescriptor("delete"),),
        ),
    ),
)


class JiraProvider(JiraClient):
    """Jira-backed issue tracker provider."""

    def describe(self) -> ProviderDescriptor:
        """Describe Jira-native resources and capabilities."""
        return JIRA_PROVIDER_DESCRIPTOR
