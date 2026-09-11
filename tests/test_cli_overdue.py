"""CLI tests for `issue overdue`."""

from click.testing import CliRunner

import jira_cli.cli as cli_module
import jira_cli.commands.query as query_module
from jira_cli.models import JiraIssue, JiraIssueField, JiraSearchResult


class DummyClient:
    def __init__(self):
        self.last_jql = None

    def search(self, jql, fields=None, max_results=50):
        self.last_jql = jql
        return JiraSearchResult(issues=[JiraIssue(key="COM-9", fields=JiraIssueField(summary="Overdue thing"))])


def test_overdue_uses_expected_jql(monkeypatch):
    client = DummyClient()
    monkeypatch.setattr(query_module, "get_jira_client", lambda *args, **kwargs: client)
    monkeypatch.setattr(query_module, "resolve_project", lambda *args, **kwargs: "COM")

    runner = CliRunner()
    result = runner.invoke(cli_module.cli, ["issue", "overdue"])

    assert result.exit_code == 0
    assert client.last_jql == "project = COM AND duedate < now() AND statusCategory != Done ORDER BY duedate ASC"
    assert "COM-9" in result.output


def test_overdue_mine_adds_current_user_clause(monkeypatch):
    client = DummyClient()
    monkeypatch.setattr(query_module, "get_jira_client", lambda *args, **kwargs: client)
    monkeypatch.setattr(query_module, "resolve_project", lambda *args, **kwargs: "COM")

    runner = CliRunner()
    result = runner.invoke(cli_module.cli, ["issue", "overdue", "--mine"])

    assert result.exit_code == 0
    assert "assignee = currentUser()" in client.last_jql
