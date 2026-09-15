"""Tests for Jira label listing without full issue model validation."""

from jira_cli.client import JiraClient


class FakeJira:
    def enhanced_search_issues(self, **kwargs):
        assert kwargs["fields"] == ["labels"]
        assert kwargs["maxResults"] is False

        class Fields:
            def __init__(self, labels):
                self.labels = labels

        class Issue:
            def __init__(self, labels):
                self.fields = Fields(labels)

        return [Issue(["backend", "urgent"]), Issue(["backend"]), Issue([])]


def test_list_labels_counts_raw_jira_label_payload() -> None:
    client = JiraClient.__new__(JiraClient)
    client.dry_run = False
    client._jira = FakeJira()

    assert client.list_labels("PROJ") == [
        {"name": "backend", "issueCount": 2},
        {"name": "urgent", "issueCount": 1},
    ]
