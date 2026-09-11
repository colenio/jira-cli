"""Tests for JiraQuery JQL composition, including the shared quick_filters clause builder
used identically by the CLI (`issue list --assignee`) and the TUI (':assignee=' command bar)."""

import pytest

from jira_cli.models import JiraSearchResult
from jira_cli.query import JiraQuery, order_by_clause


class FakeClient:
    """Captures the JQL passed to search() without hitting the network."""

    def __init__(self):
        self.last_jql = None

    def search(self, jql, fields=None, max_results=50):
        self.last_jql = jql
        return JiraSearchResult(issues=[])


def test_search_project_assignee_me_uses_current_user():
    client = FakeClient()
    JiraQuery(client).search_project(project_key="PROJ", assignee="me")
    assert client.last_jql == "project = PROJ AND assignee = currentUser()"


def test_search_project_quotes_status_and_assignee():
    client = FakeClient()
    JiraQuery(client).search_project(project_key="PROJ", status="In Progress", assignee="Marcel Körtgen")
    assert client.last_jql == (
        'project = PROJ AND status = "In Progress" AND assignee = "Marcel Körtgen"'
    )


def test_search_project_combines_all_filters_and_extra_jql():
    client = FakeClient()
    JiraQuery(client).search_project(
        project_key="PROJ", status="Done", assignee="me", label="urgent", jql_extra='priority = "High"'
    )
    assert client.last_jql == (
        'project = PROJ AND status = "Done" AND assignee = currentUser() '
        'AND labels = "urgent" AND priority = "High"'
    )


def test_search_project_filters_by_issue_type():
    client = FakeClient()
    JiraQuery(client).search_project(project_key="PROJ", issue_type="Bug")
    assert client.last_jql == 'project = PROJ AND issuetype = "Bug"'


def test_search_project_filters_by_priority_and_orders():
    client = FakeClient()
    JiraQuery(client).search_project(project_key="PROJ", priority="High", order_by="updated desc")
    assert client.last_jql == 'project = PROJ AND priority = "High" ORDER BY updated DESC'


def test_order_by_clause_rejects_unknown_fields():
    with pytest.raises(ValueError, match="Unknown order field"):
        order_by_clause("unknown desc")


def test_find_by_text_plain_text_only_searches_summary_description():
    client = FakeClient()
    JiraQuery(client).find_by_text("PROJ", "database migration")
    assert client.last_jql == (
        'project = PROJ AND (summary ~ "database migration" OR description ~ "database migration")'
    )


def test_find_by_text_issue_key_also_matches_by_key():
    """Shared by CLI `issue find` and TUI `f`: typing an issue key should find it directly,
    not just via (weaker) text search over summary/description."""
    client = FakeClient()
    JiraQuery(client).find_by_text("PROJ", "proj-123")
    assert client.last_jql == (
        'project = PROJ AND (key = PROJ-123 OR summary ~ "proj-123" OR description ~ "proj-123")'
    )


def test_find_children_uses_parent_field():
    """Shared by CLI `issue children` and TUI drill-down (`d`): covers Epic -> Story/Task
    and Story -> Sub-task alike, since Jira's own 'subtasks' field misses Epic children."""
    client = FakeClient()
    JiraQuery(client).find_children("COM-12")
    assert client.last_jql == "parent = COM-12 ORDER BY key"


def test_find_overdue_excludes_done_and_orders_by_due_date():
    client = FakeClient()
    JiraQuery(client).find_overdue("PROJ")
    assert client.last_jql == (
        "project = PROJ AND duedate < now() AND statusCategory != Done ORDER BY duedate ASC"
    )


def test_find_overdue_mine_adds_current_user_clause():
    """Shared by CLI `issue overdue --mine` and TUI `:overdue=me`."""
    client = FakeClient()
    JiraQuery(client).find_overdue("PROJ", mine=True)
    assert client.last_jql == (
        "project = PROJ AND duedate < now() AND statusCategory != Done "
        "AND assignee = currentUser() ORDER BY duedate ASC"
    )
