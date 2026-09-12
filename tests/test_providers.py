"""Tests for provider descriptors and provider-level capabilities."""

from jira_cli.providers.demo import DemoProvider
from jira_cli.providers.jira import JIRA_PROVIDER_DESCRIPTOR


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
