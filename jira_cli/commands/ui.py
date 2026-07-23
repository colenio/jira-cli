"""UI-oriented commands (TUI)."""

import click

from jira_cli.commands.common import get_jira_client, resolve_project


@click.command(name="tui")
@click.option("--project", "project", "-p", default="", help="Jira project key; defaults to JIRA_PROJECT/JIRA_PROJECT_KEY")
def launch_tui(project: str) -> None:
    """Launch interactive TUI (Terminal User Interface) for Jira issue management."""
    try:
        from jira_cli.tui.app import run_tui

        client = get_jira_client()
        project_key = resolve_project(project)
        run_tui(client, project_key)

    except ImportError:
        click.echo("TUI module could not be loaded (installation may be incomplete).", err=True)
        click.echo("Run: uv sync", err=True)
        raise SystemExit(1)
    except SystemExit:
        raise
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        raise SystemExit(1)
