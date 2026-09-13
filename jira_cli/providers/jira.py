"""Jira provider implementation."""

from __future__ import annotations

from jira_cli.client import JiraClient

from .base import ActionDescriptor, FilterDescriptor, ProviderDescriptor, ResourceDescriptor, SortDescriptor

JIRA_PROVIDER_DESCRIPTOR = ProviderDescriptor(
    name="jira",
    query_language="JQL",
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
                SortDescriptor(name="rank", field="Rank"),
            ),
            actions=(
                ActionDescriptor(name="comment"),
                ActionDescriptor(name="assign"),
                ActionDescriptor(name="transition"),
                ActionDescriptor(name="close"),
                ActionDescriptor(name="reopen"),
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
            actions=(ActionDescriptor(name="create"), ActionDescriptor(name="delete"),),
        ),
        ResourceDescriptor(
            kind="labels",
            fields=("name", "issueCount"),
        ),
    ),
)


class JiraProvider(JiraClient):
    """Jira-backed issue tracker provider."""

    def describe(self) -> ProviderDescriptor:
        """Describe Jira-native resources and capabilities."""
        return JIRA_PROVIDER_DESCRIPTOR
