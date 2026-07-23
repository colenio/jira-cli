"""CLI composition and command wiring."""

import click

from . import __version__
from .commands.issue import issue_group
from .commands.query import find_issues, list_issues, search_issues, view_issue
from .commands.ui import launch_tui
from .commands.workflow import assign_issue, transition_issue


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(version=__version__)
def cli() -> None:
    """Modular Jira CLI — list, search, view, and manage Jira issues."""


# Canonical issue command group (gh issue style)
cli.add_command(issue_group)

# Canonical `issue` subcommands for querying and workflow actions.
issue_group.add_command(list_issues, name="list")
issue_group.add_command(search_issues, name="search")
issue_group.add_command(find_issues, name="find")
issue_group.add_command(view_issue, name="view")
issue_group.add_command(assign_issue, name="assign")
issue_group.add_command(transition_issue, name="transition")

# TUI command
cli.add_command(launch_tui)


def main() -> None:
    """Main entry point."""
    cli()


if __name__ == "__main__":
    main()
