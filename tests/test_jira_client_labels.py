"""Tests for Jira label listing without full issue model validation."""

from jira_cli.client import JiraClient


class FakeJira:
    def search_issues(self, **kwargs):
        assert kwargs["fields"] == ["labels"]
        return {
            "issues": [
                {"fields": {"labels": ["backend", "urgent"]}},
                {"fields": {"labels": ["backend"]}},
                {"fields": {"labels": []}},
            ]
        }


def test_list_labels_counts_raw_jira_label_payload() -> None:
    client = JiraClient.__new__(JiraClient)
    client.dry_run = False
    client._jira = FakeJira()

    assert client.list_labels("PROJ") == [
        {"name": "backend", "issueCount": 2},
        {"name": "urgent", "issueCount": 1},
    ]
