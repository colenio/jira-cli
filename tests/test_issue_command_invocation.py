from click.testing import CliRunner

from jira_cli.cli import cli


def test_removed_top_level_list_command_fails() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["list", "--help"])

    assert result.exit_code != 0
    assert "No such command 'list'" in result.output


def test_issue_list_help_succeeds() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["issue", "list", "--help"])

    assert result.exit_code == 0
    assert "List issues in a project with optional filters" in result.output


def test_issue_create_requires_title() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["issue", "create"])

    assert result.exit_code != 0
    assert "Missing option '--title'" in result.output
