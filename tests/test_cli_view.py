"""CLI tests for view command."""

from click.testing import CliRunner

import jira_cli.cli as cli_module


class DummyClient:
    """Minimal Jira client stub for CLI tests."""

    def __init__(self, base_url: str):
        self.base_url = base_url

    def get_issue(self, key, fields=None):
        return {
            "key": key,
            "self": f"{self.base_url}/rest/api/3/issue/77931",
            "fields": {
                "summary": "Security scope clarification",
                "status": {"name": "To Do"},
                "priority": {"name": "Major"},
                "assignee": {"displayName": "Jane Doe"},
                "labels": [],
                "description": {"type": "doc"},
                "comment": {"comments": []},
            },
        }


def test_view_web_uses_issue_key_url(monkeypatch):
    """`view --web` should build browse URL using issue key, not numeric issue id."""
    opened_urls = []

    monkeypatch.setattr(
        cli_module,
        "_get_jira_client",
        lambda *args, **kwargs: DummyClient("https://example.atlassian.net"),
    )
    monkeypatch.setattr(cli_module.webbrowser, "open", lambda url: opened_urls.append(url) or True)

    runner = CliRunner()
    result = runner.invoke(cli_module.cli, ["view", "TEST-446", "--web"])

    assert result.exit_code == 0
    assert "🌐 URL: https://example.atlassian.net/browse/TEST-446" in result.output
    assert opened_urls == ["https://example.atlassian.net/browse/TEST-446"]
