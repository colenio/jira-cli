"""UI-oriented commands (TUI)."""

import click

from jira_cli.commands.common import get_jira_client, resolve_project


@click.command(name="tui")
@click.option("--project", "project", "-p", default="", help="Jira project key or GitHub Project (owner/number); defaults to JIRA_PROJECT/JIRA_PROJECT_KEY")
@click.option("--provider", "provider", default="", help="Provider context to use (jira, github, github-project, or demo)")
@click.option("--repo", "repository", "-R", default="", help="GitHub repository target (owner/name), like gh -R")
@click.option("--github-project", "gh_project", "-P", default="", help="GitHub Project V2 target (owner/number, e.g. colenio/21)")
@click.option("--demo", is_flag=True, help="Launch the TUI with synthetic demo data for safe screenshots")
def launch_tui(project: str, provider: str, repository: str, gh_project: str, demo: bool) -> None:
    """Launch interactive TUI (Terminal User Interface) for Jira/GitHub issue management."""
    try:
        from jira_cli.providers.registry import ProviderRegistry
        from jira_cli.tui.app import run_tui

        registry = ProviderRegistry()
        if gh_project:
            provider = provider or "github-project"
            project = gh_project

        context = registry.resolve_context(
            provider=provider or None, project=project or None, repository=repository or None, demo=demo
        )
        client = registry.create_or_exit(context)
        run_tui(client, context.target, context=context)

    except ImportError:
        click.echo("TUI module could not be loaded (installation may be incomplete).", err=True)
        click.echo("Run: uv sync", err=True)
        raise SystemExit(1)
    except SystemExit:
        raise
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        raise SystemExit(1)
