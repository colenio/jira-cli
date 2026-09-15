"""Tests for the dynamic ':' command-bar suggester (k9s/sofka-style autocompletion)."""

import pytest

from jira_cli.models import IssueRow
from jira_cli.tui.features.query.service import build_query_labels
from jira_cli.tui.features.query.suggester import CommandSuggester


@pytest.fixture
def issues() -> list[IssueRow]:
    return [
        IssueRow(
            key="A-1", summary="First", issue_type="Story", status="To Do", priority="High", assignee="Alice", labels="frontend"
        ),
        IssueRow(
            key="A-2", summary="Second", issue_type="Bug", status="In Progress", priority="Low", assignee="Bob", labels="backend"
        ),
    ]


@pytest.fixture
def suggester(issues) -> CommandSuggester:
    return CommandSuggester(lambda: issues)


async def test_suggests_verb(suggester):
    assert await suggester.get_suggestion("ty") == "type="


async def test_suggests_user_and_version_verbs(suggester):
    assert await suggester.get_suggestion("iss") == "issues"
    assert await suggester.get_suggestion("use") == "users"
    assert await suggester.get_suggestion("lab") == "labels"
    assert await suggester.get_suggestion("ver") == "versions"


def test_query_labels_use_provider_query_language():
    assert build_query_labels("repo", "jql", "project = repo", "GitHub issue query") == (
        "MODE: GITHUB ISSUE QUERY",
        "Source: github issue query project = repo",
    )


async def test_suggests_value_after_verb(suggester):
    assert await suggester.get_suggestion("type=st") == "type=Story"


async def test_suggests_assignee_from_external_user_catalog(issues):
    suggester = CommandSuggester(lambda: issues, lambda: ["Tobias Braun", "Andreas Bauer"])

    assert await suggester.get_suggestion("assignee=Tob") == "assignee=Tobias Braun"


async def test_suggests_contextual_resource_action(issues):
    suggester = CommandSuggester(lambda: issues, verbs_provider=lambda: ["labels", "create", "edit"])

    assert await suggester.get_suggestion("cre") == "create"
    assert await suggester.get_suggestion("del") is None


async def test_suggests_priority_value(suggester):
    assert await suggester.get_suggestion("priority=h") == "priority=High"


async def test_suggests_order_field(suggester):
    assert await suggester.get_suggestion("order=pr") == "order=priority"


async def test_no_suggestion_for_unknown_value(suggester):
    assert await suggester.get_suggestion("type=zzz") is None


async def test_empty_value_has_no_suggestion(suggester):
    assert await suggester.get_suggestion("") is None
