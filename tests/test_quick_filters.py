"""Tests for QuickFilterResolver: the shared, class-based quick-filter resolution logic
used identically by the CLI (JiraQuery.search_project) and the TUI (':' command bar)."""

from jira_cli.quick_filters import QuickFilterResolver
from jira_cli.providers.base import ProviderDescriptor


class FakeClient:
    def __init__(self, assignable_users=None):
        self.assignable_users = [
            user if isinstance(user, dict) else {"displayName": user}
            for user in (assignable_users or [])
        ]

    def find_assignable_users(self, project_key, query, max_results=20):
        return list(self.assignable_users)

    def describe(self):
        return ProviderDescriptor(name="jira")


class FakeGitHubClient(FakeClient):
    def describe(self):
        return ProviderDescriptor(name="github")


def test_clause_builds_quoted_field_equality():
    resolver = QuickFilterResolver(FakeClient(), "PROJ")
    assert resolver.clause("status", "In Progress") == 'status = "In Progress"'


def test_clause_key_is_uppercased_and_unquoted():
    resolver = QuickFilterResolver(FakeClient(), "PROJ")
    assert resolver.clause("key", "proj-123") == "key = PROJ-123"


def test_clause_assignee_me_uses_current_user():
    resolver = QuickFilterResolver(FakeClient(), "PROJ")
    assert resolver.clause("assignee", "me") == "assignee = currentUser()"


def test_clause_assignee_none_uses_jira_empty_operator():
    resolver = QuickFilterResolver(FakeClient(), "PROJ")
    assert resolver.clause("assignee", "none") == "assignee is EMPTY"
    assert resolver.resolve("assignee", "unassigned")[1] == "assignee is EMPTY"


def test_clause_assignee_none_uses_github_unassigned_value():
    resolver = QuickFilterResolver(FakeGitHubClient(), "owner/repo")
    assert resolver.clause("assignee", "none") == "assignee = none"


def test_resolve_prefers_known_values_over_server_lookup():
    resolver = QuickFilterResolver(FakeClient(assignable_users=["Should Not Be Used"]), "PROJ")
    display_value, clause = resolver.resolve("assignee", "koertgen", known_values=["Marcel Körtgen"])
    assert display_value == "Marcel Körtgen"
    assert clause == 'assignee = "Marcel Körtgen"'


def test_resolve_falls_back_to_server_side_assignable_users():
    resolver = QuickFilterResolver(FakeClient(assignable_users=["Marcel Körtgen"]), "PROJ")
    display_value, clause = resolver.resolve("assignee", "koertgen", known_values=[])
    assert display_value == "Marcel Körtgen"
    assert clause == 'assignee = "Marcel Körtgen"'


def test_resolve_assignee_uses_account_id_for_jira_clause():
    resolver = QuickFilterResolver(
        FakeClient(assignable_users=[{"displayName": "Andreas Bauer", "accountId": "jira-account-123"}]),
        "PROJ",
    )

    display_value, clause = resolver.resolve("assignee", "Andreas Bauer", known_values=["Andreas Bauer"])

    assert display_value == "Andreas Bauer"
    assert clause == 'assignee = "jira-account-123"'


def test_resolve_falls_back_to_raw_value_when_nothing_matches():
    resolver = QuickFilterResolver(FakeClient(), "PROJ")
    display_value, clause = resolver.resolve("assignee", "nobody", known_values=[])
    assert display_value == "nobody"
    assert clause == 'assignee = "nobody"'


def test_resolve_assignee_me_short_circuits_before_any_lookup():
    resolver = QuickFilterResolver(FakeClient(assignable_users=["Should Not Be Used"]), "PROJ")
    display_value, clause = resolver.resolve("assignee", "me", known_values=["Also Not Used"])
    assert display_value == "me"
    assert clause == "assignee = currentUser()"
