"""Tests for synthetic demo data used by the TUI screenshot mode."""

from jira_cli.demo import DEMO_PROJECT_KEY, DemoJiraClient
from jira_cli.models import IssueRow
from jira_cli.query import JiraQuery


def test_demo_client_searches_and_filters_like_jira_query() -> None:
    client = DemoJiraClient()
    rows = JiraQuery(client).search_project(DEMO_PROJECT_KEY, priority="Highest", order_by="updated desc")

    assert [row.key for row in rows] == ["DEMO-3"]
    assert rows[0].assignee == "Marcel Körtgen"


def test_demo_epic_planning_dates_reach_timeline_rows() -> None:
    rows = JiraQuery(DemoJiraClient()).search_project(DEMO_PROJECT_KEY, max_results=100)
    epics = {row.key: row for row in rows if row.issue_type == "Epic"}

    assert epics["DEMO-10"].start_date == "2026-08-01"
    assert epics["DEMO-10"].due_date == "2026-10-31"


def test_demo_version_navigation_filters_by_fix_version() -> None:
    rows = JiraQuery(DemoJiraClient()).search_custom_jql(f'project = {DEMO_PROJECT_KEY} AND fixVersion = "v0.5.0"')

    assert sorted(row.key for row in rows) == ["DEMO-3", "DEMO-4"]
    assert all("v0.5.0" in row.versions for row in rows)


def test_demo_provider_exposes_sprints_components_and_navigation() -> None:
    from jira_cli.providers.demo import DemoProvider

    provider = DemoProvider()
    query = JiraQuery(provider)
    sprints = provider.list_resource("sprints", DEMO_PROJECT_KEY)
    components = provider.list_resource("components", DEMO_PROJECT_KEY)

    assert [sprint["state"] for sprint in sprints] == ["active", "future", "future", "closed", "closed"]
    active_query = provider.resource_issue_query("sprints", sprints[0], DEMO_PROJECT_KEY)
    assert sorted(row.key for row in query.search_custom_jql(active_query)) == ["DEMO-1", "DEMO-3", "DEMO-4"]
    tui_query = provider.resource_issue_query("components", next(c for c in components if c["name"] == "TUI"), DEMO_PROJECT_KEY)
    assert [row.key for row in query.search_custom_jql(tui_query)] == ["DEMO-3"]
    assert provider.list_epic_sprint_assignments(DEMO_PROJECT_KEY)["DEMO-10"] == ["102", "103"]


def test_demo_labels_always_have_stable_palette_colors() -> None:
    from jira_cli.tui.features.labels.service import list_project_labels

    client = DemoJiraClient()
    labels = list_project_labels(client, DEMO_PROJECT_KEY)
    repeated = list_project_labels(client, DEMO_PROJECT_KEY)

    assert labels
    assert all(label["themeColor"].startswith("bright_") for label in labels)
    assert {label["name"]: label["themeColor"] for label in labels} == {
        label["name"]: label["themeColor"] for label in repeated
    }


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
