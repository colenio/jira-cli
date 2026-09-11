"""CLI tests for the `user` command group."""

from click.testing import CliRunner

import jira_cli.cli as cli_module
import jira_cli.commands.user as user_module


class DummyClient:
    def get_current_user(self):
        return {"displayName": "Marcel Körtgen", "emailAddress": "marcel@example.com", "accountId": "abc123"}

    def search_users(self, query, max_results=20):
        return [{"displayName": "Marcel Körtgen", "emailAddress": "marcel@example.com", "active": True}]

    def list_assignable_users(self, project_key, max_results=50):
        return [{"displayName": "Marcel Körtgen", "emailAddress": "marcel@example.com", "active": True}]


def test_user_me_shows_current_account(monkeypatch):
    client = DummyClient()
    monkeypatch.setattr(user_module, "get_jira_client", lambda *args, **kwargs: client)

    result = CliRunner().invoke(cli_module.cli, ["user", "me"])

    assert result.exit_code == 0
    assert "Marcel Körtgen" in result.output
    assert "marcel@example.com" in result.output


def test_user_search_shows_matches(monkeypatch):
    client = DummyClient()
    monkeypatch.setattr(user_module, "get_jira_client", lambda *args, **kwargs: client)

    result = CliRunner().invoke(cli_module.cli, ["user", "search", "koertgen"])

    assert result.exit_code == 0
    assert "Marcel Körtgen" in result.output


def test_user_list_shows_project_assignable_users(monkeypatch):
    client = DummyClient()
    monkeypatch.setattr(user_module, "get_jira_client", lambda *args, **kwargs: client)
    monkeypatch.setattr(user_module, "resolve_project", lambda *args, **kwargs: "COM")

    result = CliRunner().invoke(cli_module.cli, ["user", "list"])

    assert result.exit_code == 0
    assert "Marcel Körtgen" in result.output


def test_user_search_falls_back_to_assignable_users_when_global_search_is_restricted(monkeypatch):
    """Jira Cloud's global user search silently returns [] without the 'Browse users and
    groups' permission (common in locked-down orgs). We must not report 'no results' in
    that case if the project-scoped assignable-users search (needs only 'Browse Projects')
    actually finds a match, and the email must carry through (not a placeholder)."""

    class RestrictedClient:
        def search_users(self, query, max_results=20):
            return []

        def find_assignable_users(self, project_key, query, max_results=20):
            assert project_key == "COM"
            return [{"displayName": "Melvin Klimke", "emailAddress": "melvin@example.com", "active": True}]

    client = RestrictedClient()
    monkeypatch.setattr(user_module, "get_jira_client", lambda *args, **kwargs: client)
    monkeypatch.setenv("JIRA_PROJECT", "COM")

    result = CliRunner().invoke(cli_module.cli, ["user", "search", "melvin"])

    assert result.exit_code == 0
    assert "Melvin Klimke" in result.output
    assert "melvin@example.com" in result.output
