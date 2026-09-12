"""Tests for synthetic demo data used by the TUI screenshot mode."""

from jira_cli.demo import DEMO_PROJECT_KEY, DemoJiraClient
from jira_cli.models import IssueRow
from jira_cli.query import JiraQuery


def test_demo_client_searches_and_filters_like_jira_query() -> None:
    client = DemoJiraClient()
    rows = JiraQuery(client).search_project(DEMO_PROJECT_KEY, priority="Highest", order_by="updated desc")

    assert [row.key for row in rows] == ["DEMO-3"]
    assert rows[0].assignee == "Marcel Körtgen"


def test_demo_client_supports_tui_resource_views() -> None:
    client = DemoJiraClient()

    users = client.search_users("grace")
    versions = client.list_versions(DEMO_PROJECT_KEY)
    comments = client.get_issue_comments("DEMO-3")

    assert users[0]["displayName"] == "Grace Hopper"
    assert versions[0]["name"] == "v0.5.0"
    assert "prefetch" in comments[0]["body"]


def test_demo_client_current_user_matches_assignee_me() -> None:
    client = DemoJiraClient()
    rows = JiraQuery(client).search_project(DEMO_PROJECT_KEY, assignee="me")

    assert client.get_current_user()["displayName"] == "Marcel Körtgen"
    assert {IssueRow.model_validate(row).assignee for row in rows} == {"Marcel Körtgen"}
