"""Provider contracts and descriptors for issue tracker integrations."""

from __future__ import annotations

from typing import Optional, Protocol

from pydantic import BaseModel, ConfigDict

from jira_cli.models import JiraSearchResult


class FilterDescriptor(BaseModel):
    """A filter supported by a provider resource."""

    model_config = ConfigDict(frozen=True)

    name: str
    field: str
    special_values: tuple[str, ...] = ()


class SortDescriptor(BaseModel):
    """A sort supported by a provider resource."""

    model_config = ConfigDict(frozen=True)

    name: str
    field: str
    default_direction: str = "asc"


class ActionDescriptor(BaseModel):
    """An action supported by a provider resource."""

    model_config = ConfigDict(frozen=True)

    name: str
    requires_comment: bool = False


class ResourceDescriptor(BaseModel):
    """A provider resource kind and its supported fields, filters, sorts, and actions."""

    model_config = ConfigDict(frozen=True)

    kind: str
    fields: tuple[str, ...] = ()
    filters: tuple[FilterDescriptor, ...] = ()
    sorts: tuple[SortDescriptor, ...] = ()
    actions: tuple[ActionDescriptor, ...] = ()


class ProviderDescriptor(BaseModel):
    """Static provider metadata used by CLI/TUI surfaces to discover capabilities."""

    model_config = ConfigDict(frozen=True)

    name: str
    query_language: str = "query"
    supports_board: bool = True
    resources: tuple[ResourceDescriptor, ...] = ()

    def resource(self, kind: str) -> ResourceDescriptor | None:
        """Return a resource descriptor by kind."""
        for resource in self.resources:
            if resource.kind == kind:
                return resource
        return None


class ProviderContext(BaseModel):
    """An active provider plus its target project/repository context."""

    model_config = ConfigDict(frozen=True)

    name: str
    provider: str
    target: str
    label: str


class IssueTrackerProvider(Protocol):
    """Shared provider surface currently used by CLI, TUI, and query services."""

    base_url: str
    dry_run: bool

    def describe(self) -> ProviderDescriptor:
        """Describe provider resources, filters, sorts, and actions."""
        ...

    def get_issue_url(self, key: str) -> str:
        """Return the web URL for an issue key."""
        ...

    def search(
        self,
        jql: str,
        fields: Optional[list[str]] = None,
        start_at: int = 0,
        max_results: int = 50,
        expand: Optional[list[str]] = None,
    ) -> JiraSearchResult:
        """Search issues using the provider-native query string currently understood by JiraQuery."""
        ...

    def get_current_user(self) -> dict:
        """Return the authenticated/current user."""
        ...

    def list_assignable_users(self, project_key: str, max_results: int = 50) -> list[dict]:
        """List users assignable in a project/repository context."""
        ...

    def find_assignable_users(self, project_key: str, query: str, max_results: int = 20) -> list[dict]:
        """Search assignable users in a project/repository context."""
        ...

    def search_users(self, query: str, max_results: int = 20) -> list[dict]:
        """Search users globally or with provider-specific fallback."""
        ...

    def list_versions(self, project_key: str) -> list[dict]:
        """List milestones/versions for a project/repository context."""
        ...

    def create_version(self, project_key: str, name: str, description: str = "", release_date: str | None = None) -> dict:
        """Create a version or milestone."""
        ...

    def update_version(self, project_key: str, name: str, **fields) -> dict:
        """Update a version or milestone by name."""
        ...

    def delete_version(self, project_key: str, name: str) -> bool:
        """Delete a version or milestone by name."""
        ...

    def list_labels(self, project_key: str) -> list[dict]:
        """List labels/tags for a project/repository context."""
        ...

    def create_label(self, project_key: str, name: str, color: str, description: str = "") -> dict:
        """Create a label in the active provider context."""
        ...

    def update_label(
        self, project_key: str, name: str, new_name: str, color: str, description: str = ""
    ) -> dict:
        """Update a label in the active provider context."""
        ...

    def delete_label(self, project_key: str, name: str) -> None:
        """Delete a label from the active provider context."""
        ...

    def get_issue_comments(self, key: str, expand_changelog: bool = False) -> list[dict]:
        """List comments for an issue."""
        ...

    def find_children(self, key: str, max_results: int = 50) -> list:
        """Return child issues for a provider-native issue hierarchy."""
        ...

    def add_comment(self, key: str, body: str | dict, use_adf: bool = False) -> dict:
        """Add a comment to an issue."""
        ...

    def update_issue(self, key: str, fields: dict) -> None:
        """Update supported issue fields, such as the summary/title."""
        ...

    def create_issue(
        self,
        project_key: str,
        title: str,
        body: str | dict | None = None,
        issue_type: str = "Task",
        labels: list[str] | None = None,
        assignee: str | None = None,
        priority: str | None = None,
        parent: str | None = None,
        repository: str | None = None,
    ) -> dict:
        """Create an issue in the active provider context."""
        ...

    def list_issue_repositories(self) -> list[str]:
        """List repositories available for issue creation in this context."""
        ...

    def get_transitions(self, key: str) -> list[dict]:
        """List transitions/actions available for an issue."""
        ...

    def transition_issue(self, key: str, transition_id: str, comment: str | None = None) -> None:
        """Transition an issue by provider-native action id."""
        ...

    def assign_issue(self, key: str, account_id: str) -> None:
        """Assign an issue."""
        ...
