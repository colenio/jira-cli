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
            fields=("key", "summary", "type", "status", "assignee", "reporter", "priority", "labels", "updated", "parent"),
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
                ActionDescriptor(name="create"),
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
            actions=(
                ActionDescriptor(name="create"),
                ActionDescriptor(name="edit"),
                ActionDescriptor(name="delete"),
                ActionDescriptor(name="release"),
            ),
        ),
        ResourceDescriptor(
            kind="labels",
            fields=("name", "issueCount"),
            actions=(ActionDescriptor(name="edit"), ActionDescriptor(name="delete")),
        ),
    ),
)


class JiraProvider(JiraClient):
    """Jira-backed issue tracker provider."""

    def describe(self) -> ProviderDescriptor:
        """Describe Jira-native resources and capabilities."""
        return JIRA_PROVIDER_DESCRIPTOR

    def update_label(
        self, project_key: str, name: str, new_name: str, color: str, description: str = ""
    ) -> dict:
        """Rename a Jira label on every matching issue in the project."""
        issues = self._jira.enhanced_search_issues(
            jql_str=f'project = {project_key} AND labels = "{name}"',
            maxResults=False,
            fields=["labels"],
        )
        for issue in issues:
            labels = [new_name if label == name else label for label in (issue.fields.labels or [])]
            issue.update(fields={"labels": list(dict.fromkeys(labels))})
        return {"name": new_name, "issueCount": len(issues)}

    def delete_label(self, project_key: str, name: str) -> None:
        """Remove a Jira label from every matching issue in the project."""
        issues = self._jira.enhanced_search_issues(
            jql_str=f'project = {project_key} AND labels = "{name}"',
            maxResults=False,
            fields=["labels"],
        )
        for issue in issues:
            issue.update(fields={"labels": [label for label in (issue.fields.labels or []) if label != name]})
