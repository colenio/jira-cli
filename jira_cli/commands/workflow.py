"""Workflow/action commands for Jira issues."""

import click

from jira_cli.commands.common import get_jira_client


@click.command(name="assign")
@click.argument("key")
@click.argument("assignee")
def assign_issue(key: str, assignee: str) -> None:
    """Assign issue to user."""
    try:
        client = get_jira_client()
        client.assign_issue(key, assignee)
        click.echo(f"Assigned {key} to {assignee}")

    except SystemExit:
        raise
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        raise SystemExit(1)


@click.command(name="transition")
@click.argument("key")
@click.argument("transition_id")
@click.option("--comment", "comment", default="", help="Optional transition comment")
def transition_issue(key: str, transition_id: str, comment: str) -> None:
    """Transition issue to new status."""
    try:
        client = get_jira_client()
        client.transition_issue(key, transition_id, comment=comment or None)
        click.echo(f"Transitioned {key} to {transition_id}")

    except SystemExit:
        raise
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        raise SystemExit(1)
