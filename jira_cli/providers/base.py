"""Provider contracts and descriptors for issue tracker integrations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Protocol

from jira_cli.models import JiraSearchResult


@dataclass(frozen=True)
class FilterDescriptor:
    """A filter supported by a provider resource."""

    name: str
    field: str
    special_values: tuple[str, ...] = ()


@dataclass(frozen=True)
class SortDescriptor:
    """A sort supported by a provider resource."""

    name: str
    field: str
    default_direction: str = "asc"


@dataclass(frozen=True)
class ActionDescriptor:
    """An action supported by a provider resource."""

    name: str
    requires_comment: bool = False


@dataclass(frozen=True)
class ResourceDescriptor:
    """A provider resource kind and its supported fields, filters, sorts, and actions."""

    kind: str
    fields: tuple[str, ...] = ()
    filters: tuple[FilterDescriptor, ...] = ()
    sorts: tuple[SortDescriptor, ...] = ()
    actions: tuple[ActionDescriptor, ...] = ()


@dataclass(frozen=True)
class ProviderDescriptor:
    """Static provider metadata used by CLI/TUI surfaces to discover capabilities."""

    name: str
    resources: tuple[ResourceDescriptor, ...] = field(default_factory=tuple)

    def resource(self, kind: str) -> ResourceDescriptor | None:
        """Return a resource descriptor by kind."""
        for resource in self.resources:
            if resource.kind == kind:
                return resource
        return None


class IssueTrackerProvider(Protocol):
    """Shared provider surface currently used by CLI, TUI, and query services."""

    base_url: str
    dry_run: bool

    def describe(self) -> ProviderDescriptor:
        """Describe provider resources, filters, sorts, and actions."""
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

    def get_issue_comments(self, key: str, expand_changelog: bool = False) -> list[dict]:
        """List comments for an issue."""
        ...

    def add_comment(self, key: str, body: str | dict, use_adf: bool = False) -> dict:
        """Add a comment to an issue."""
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
