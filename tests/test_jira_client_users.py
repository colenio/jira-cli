"""Tests for Jira Cloud current-user and assignment behavior."""

from types import SimpleNamespace

from jira_cli.client import JiraClient


def test_current_user_uses_configured_email_when_jira_redacts_it() -> None:
    client = JiraClient.__new__(JiraClient)
    client.dry_run = False
    client.email = "dennis@example.com"
    client._jira = SimpleNamespace(myself=lambda: {"accountId": "account-123", "displayName": "Dennis"})

    user = client.get_current_user()

    assert user["emailAddress"] == "dennis@example.com"


def test_assign_me_uses_current_account_id_without_user_search() -> None:
    updates = []

    class Issue:
        def update(self, fields):
            updates.append(fields)

    client = JiraClient.__new__(JiraClient)
    client.dry_run = False
    client.get_current_user = lambda: {"accountId": "account-123"}
    client._jira = SimpleNamespace(issue=lambda key: Issue(), assign_issue=lambda *_: (_ for _ in ()).throw(AssertionError("unexpected user lookup")))

    client.assign_issue("TIST-1", "me")

    assert updates == [{"assignee": {"accountId": "account-123"}}]
