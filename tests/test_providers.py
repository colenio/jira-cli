"""Tests for provider descriptors and provider-level capabilities."""

from jira_cli.providers.demo import DemoProvider
from jira_cli.providers.github import GITHUB_PROVIDER_DESCRIPTOR, GitHubProvider
from jira_cli.providers.jira import JIRA_PROVIDER_DESCRIPTOR
from jira_cli.providers.registry import ProviderRegistry


def test_jira_provider_describes_issue_filters_and_actions() -> None:
    issues = JIRA_PROVIDER_DESCRIPTOR.resource("issues")

    assert issues is not None
    assert {item.name for item in issues.filters} >= {"type", "status", "assignee", "priority", "key"}
    assert {item.name for item in issues.actions} >= {"comment", "assign", "transition"}


def test_demo_provider_describes_same_core_resources() -> None:
    descriptor = DemoProvider().describe()

    assert descriptor.name == "demo"
    assert descriptor.resource("issues") is not None
    assert descriptor.resource("users") is not None
    assert descriptor.resource("versions") is not None


def test_github_provider_describes_read_only_resources() -> None:
    issues = GITHUB_PROVIDER_DESCRIPTOR.resource("issues")
    labels = GITHUB_PROVIDER_DESCRIPTOR.resource("labels")

    assert issues is not None
    assert labels is not None
    assert GITHUB_PROVIDER_DESCRIPTOR.query_language == "GitHub issue query"
    assert {item.name for item in issues.filters} >= {"status", "assignee", "label", "milestone", "key"}
    assert {item.name for item in issues.sorts} >= {"created", "updated", "comments"}
    assert not issues.actions


def test_descriptor_resource_lookup_returns_none_for_unknown_kind() -> None:
    assert DemoProvider().describe().resource("unknown") is None


def test_registry_always_exposes_demo_context(monkeypatch) -> None:
    monkeypatch.delenv("JIRA_URL", raising=False)
    monkeypatch.delenv("JIRA_EMAIL", raising=False)
    monkeypatch.delenv("JIRA_API_TOKEN", raising=False)
    monkeypatch.setattr(ProviderRegistry, "github_token", staticmethod(lambda: ""))

    contexts = ProviderRegistry(load_env=False).available_contexts()

    assert [context.name for context in contexts] == ["demo"]


def test_registry_resolves_explicit_demo_target() -> None:
    context = ProviderRegistry(load_env=False).resolve_context(provider="demo", project="SANDBOX")

    assert context.provider == "demo"
    assert context.target == "SANDBOX"
    assert context.label == "Demo / SANDBOX"


def test_registry_resolves_jira_context_from_env(monkeypatch) -> None:
    monkeypatch.setenv("JIRA_PROJECT", "COM")

    context = ProviderRegistry(load_env=False).resolve_context(provider="jira")

    assert context.name == "jira:COM"
    assert context.provider == "jira"
    assert context.target == "COM"


def test_registry_resolves_explicit_github_repository() -> None:
    context = ProviderRegistry(load_env=False).resolve_context(provider="github", repository="colenio/jira-cli")

    assert context.name == "github:colenio/jira-cli"
    assert context.provider == "github"
    assert context.target == "colenio/jira-cli"


def test_registry_parses_github_remotes() -> None:
    assert ProviderRegistry.parse_github_remote("git@github.com:colenio/jira-cli.git") == "colenio/jira-cli"
    assert ProviderRegistry.parse_github_remote("https://github.com/colenio/jira-cli.git") == "colenio/jira-cli"
    assert ProviderRegistry.parse_github_remote("git@github.com:acme/repo.with.dots.git") == "acme/repo.with.dots"


def test_github_provider_descriptor_method_without_network() -> None:
    provider = GitHubProvider.__new__(GitHubProvider)

    assert provider.describe().name == "github"


def test_github_label_dict_includes_issue_count() -> None:
    from jira_cli.providers.github import _label_dict

    class Label:
        name = "bug"
        color = "d73a4a"
        description = "Something is not working"

    assert _label_dict(Label(), issue_count=3) == {
        "name": "bug",
        "color": "d73a4a",
        "description": "Something is not working",
        "issueCount": 3,
    }


def test_parse_project_target() -> None:
    from jira_cli.providers.github_project import parse_project_target

    assert parse_project_target("colenio/21") == ("colenio", 21)
    assert parse_project_target("orgs/colenio/projects/21") == ("colenio", 21)
    assert parse_project_target("21", default_owner="colenio") == ("colenio", 21)


def test_registry_resolves_github_project_context() -> None:
    context = ProviderRegistry(load_env=False).resolve_context(provider="github-project", project="colenio/21")

    assert context.name == "github-project:colenio/21"
    assert context.provider == "github-project"
    assert context.target == "colenio/21"
    assert context.label == "GitHub Project / colenio/21"


def test_registry_auto_detects_single_context(monkeypatch) -> None:
    monkeypatch.setenv("GH_PROJECT", "colenio/21")
    monkeypatch.setattr(ProviderRegistry, "github_token", staticmethod(lambda: "ghp_fake"))

    # When no provider requested, auto-detect single available real context
    context = ProviderRegistry(load_env=False).resolve_context(interactive=False)

    assert context.provider == "github-project"
    assert context.target == "colenio/21"


def test_registry_interactive_context_selection(monkeypatch) -> None:
    monkeypatch.setenv("GH_PROJECT", "colenio/21")
    monkeypatch.setenv("JIRA_URL", "https://example.atlassian.net")
    monkeypatch.setenv("JIRA_EMAIL", "test@example.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "token")
    monkeypatch.setenv("JIRA_PROJECT", "COM")
    monkeypatch.setattr(ProviderRegistry, "github_token", staticmethod(lambda: "ghp_fake"))

    # Mock interactive prompt returning option 1 (github-project)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("click.prompt", lambda prompt, type, default, err: 1)

    context = ProviderRegistry(load_env=False).resolve_context(interactive=True)

    assert context.provider == "github-project"
    assert context.target == "colenio/21"


def test_github_project_provider_to_jira_issue() -> None:
    from jira_cli.providers.github_project import GitHubProjectProvider

    provider = GitHubProjectProvider.__new__(GitHubProjectProvider)
    provider._status_options = {"Todo": "opt1", "In Progress": "opt2", "Done": "opt3"}
    provider._item_cache = {}

    node = {
        "id": "PVTI_123456",
        "type": "ISSUE",
        "content": {
            "number": 42,
            "title": "Test Issue",
            "repository": {"nameWithOwner": "colenio/jira-cli"},
            "assignees": {"nodes": [{"login": "mkoertgen", "name": "Marcel Körtgen"}]},
            "labels": {"nodes": [{"name": "enhancement"}]},
            "body": "Test body",
        },
        "fieldValueByName": {"name": "In Progress", "optionId": "opt2"},
        "updatedAt": "2026-09-13T10:00:00Z",
    }

    issue = provider._to_jira_issue(node)

    assert issue.key == "jira-cli#42"
    assert issue.fields.summary == "Test Issue"
    assert issue.fields.status == {"name": "In Progress"}
    assert issue.fields.assignee == {"accountId": "mkoertgen", "displayName": "Marcel Körtgen"}
    assert issue.fields.labels == ["enhancement"]

    transitions = provider.list_transitions("jira-cli#42")
    assert {t["name"] for t in transitions} == {"Todo", "Done"}
