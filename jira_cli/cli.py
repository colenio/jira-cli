"""CLI composition and command wiring."""

import click

from . import __version__
from .commands.issue import issue_close, issue_comment, issue_create, issue_edit, issue_group, issue_reopen
from .commands.query import children_issues, find_issues, list_issues, overdue_issues, search_issues, view_issue
from .commands.ui import launch_tui
from .commands.validate import validate_contexts
from .commands.user import user_group
from .commands.version import version_group
from .commands.workflow import assign_issue, transition_issue


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(version=__version__)
def cli() -> None:
    """Modular Jira CLI — list, search, view, and manage Jira issues."""


# Canonical issue command group (gh issue style)
cli.add_command(issue_group)

# Curated order (see commands.common.OrderedGroup) for `jira issue --help`, read -> act,
# not alphabetical: browse/find the issue, then act on it.
issue_group.add_command(list_issues, name="list")
issue_group.add_command(search_issues, name="search")
issue_group.add_command(find_issues, name="find")
issue_group.add_command(view_issue, name="view")
issue_group.add_command(children_issues, name="children")
issue_group.add_command(overdue_issues, name="overdue")
issue_group.add_command(issue_create, name="create")
issue_group.add_command(issue_edit, name="edit")
issue_group.add_command(issue_comment, name="comment")
issue_group.add_command(assign_issue, name="assign")
issue_group.add_command(transition_issue, name="transition")
issue_group.add_command(issue_close, name="close")
issue_group.add_command(issue_reopen, name="reopen")

# TUI command
cli.add_command(launch_tui)
cli.add_command(validate_contexts)

# Additional top-level command groups, gh-style (gh issue / gh pr / gh repo)
cli.add_command(version_group)
cli.add_command(user_group)


def main() -> None:
    """Main entry point."""
    cli()


if __name__ == "__main__":
    main()
