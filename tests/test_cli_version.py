"""CLI tests for the `version` command group (fix versions / milestones)."""

from click.testing import CliRunner

import jira_cli.cli as cli_module
import jira_cli.commands.version as version_module


class DummyClient:
    def __init__(self):
        self.versions = [
            {"name": "v1.0", "released": True, "archived": False, "releaseDate": "2026-01-01"},
            {"name": "v2.0", "released": False, "archived": False, "releaseDate": None},
        ]
        self.created = None
        self.deleted = None

    def list_versions(self, project_key):
        return self.versions

    def create_version(self, project_key, name, description="", release_date=None):
        self.created = (project_key, name, description, release_date)
        return {"name": name}

    def delete_version(self, project_key, name):
        self.deleted = (project_key, name)
        return name == "v2.0"


def test_version_list_shows_all_versions(monkeypatch):
    client = DummyClient()
    monkeypatch.setattr(version_module, "get_jira_client", lambda *args, **kwargs: client)
    monkeypatch.setattr(version_module, "resolve_project", lambda *args, **kwargs: "COM")

    result = CliRunner().invoke(cli_module.cli, ["version", "list"])

    assert result.exit_code == 0
    assert "v1.0" in result.output
    assert "v2.0" in result.output
    assert "2 version(s)" in result.output


def test_version_create_passes_through_fields(monkeypatch):
    client = DummyClient()
    monkeypatch.setattr(version_module, "get_jira_client", lambda *args, **kwargs: client)
    monkeypatch.setattr(version_module, "resolve_project", lambda *args, **kwargs: "COM")

    result = CliRunner().invoke(
        cli_module.cli, ["version", "create", "--name", "v3.0", "--release-date", "2026-06-01"]
    )

    assert result.exit_code == 0
    assert client.created == ("COM", "v3.0", "", "2026-06-01")


def test_version_delete_missing_version_exits_nonzero(monkeypatch):
    client = DummyClient()
    monkeypatch.setattr(version_module, "get_jira_client", lambda *args, **kwargs: client)
    monkeypatch.setattr(version_module, "resolve_project", lambda *args, **kwargs: "COM")

    result = CliRunner().invoke(cli_module.cli, ["version", "delete", "does-not-exist"])

    assert result.exit_code == 1
    assert client.deleted == ("COM", "does-not-exist")
