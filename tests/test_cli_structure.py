from click.testing import CliRunner

from jira_cli.cli import cli


REQUIRED_ISSUE_COMMANDS = {
    "assign",
    "close",
    "comment",
    "create",
    "edit",
    "find",
    "list",
    "reopen",
    "search",
    "transition",
    "view",
}


def test_root_has_only_issue_and_tui_commands() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])

    assert result.exit_code == 0
    assert "  issue  " in result.output
    assert "  tui    " in result.output

    # Explicitly ensure old top-level commands are gone.
    assert "\n  list" not in result.output
    assert "\n  create" not in result.output
    assert "\n  comment" not in result.output
    assert "\n  close" not in result.output


def test_issue_group_contains_expected_commands() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["issue", "--help"])

    assert result.exit_code == 0
    for name in REQUIRED_ISSUE_COMMANDS:
        assert name in result.output
