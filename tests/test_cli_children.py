"""CLI tests for the `issue children` command."""

from click.testing import CliRunner

import jira_cli.cli as cli_module
import jira_cli.commands.query as query_module
from jira_cli.models import JiraIssue, JiraIssueField, JiraSearchResult


class DummyClient:
    """Minimal Jira client stub for CLI tests."""

    def __init__(self):
        self.last_jql = None

    def search(self, jql, fields=None, max_results=50):
        self.last_jql = jql
        return JiraSearchResult(
            issues=[JiraIssue(key="COM-13", fields=JiraIssueField(summary="Story under epic"))]
        )


def test_children_uses_parent_jql(monkeypatch):
    client = DummyClient()
    monkeypatch.setattr(query_module, "get_jira_client", lambda *args, **kwargs: client)

    runner = CliRunner()
    result = runner.invoke(cli_module.cli, ["issue", "children", "COM-12"])

    assert result.exit_code == 0
    assert client.last_jql == "parent = COM-12 ORDER BY key"
    assert "COM-13" in result.output
