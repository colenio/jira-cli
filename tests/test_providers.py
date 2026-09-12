"""Tests for provider descriptors and provider-level capabilities."""

from jira_cli.providers.demo import DemoProvider
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


def test_descriptor_resource_lookup_returns_none_for_unknown_kind() -> None:
    assert DemoProvider().describe().resource("unknown") is None


def test_registry_always_exposes_demo_context(monkeypatch) -> None:
    monkeypatch.delenv("JIRA_URL", raising=False)
    monkeypatch.delenv("JIRA_EMAIL", raising=False)
    monkeypatch.delenv("JIRA_API_TOKEN", raising=False)

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
