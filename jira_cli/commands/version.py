"""Fix version (milestone) management commands."""

import click

from jira_cli.commands.common import OrderedGroup, get_jira_client, resolve_project
from jira_cli.render import JiraRenderer


@click.group(name="version", cls=OrderedGroup)
def version_group() -> None:
    """Manage Jira fix versions (milestones)."""


@version_group.command(name="list")
@click.option("--project", "project", "-p", default="", help="Jira project key; defaults to JIRA_PROJECT/JIRA_PROJECT_KEY")
def version_list(project: str) -> None:
    """List fix versions (milestones) in a project."""
    try:
        client = get_jira_client()
        renderer = JiraRenderer()
        project_key = resolve_project(project)
        versions = client.list_versions(project_key)

        renderer.versions_table(versions, title=f"Versions in {project_key}")

    except SystemExit:
        raise
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        raise SystemExit(1)


@version_group.command(name="create")
@click.option("--project", "project", "-p", default="", help="Jira project key; defaults to JIRA_PROJECT/JIRA_PROJECT_KEY")
@click.option("--name", "name", "-n", required=True, help="Version name")
@click.option("--description", "description", default="", help="Version description")
@click.option("--release-date", "release_date", default="", help="Release date (YYYY-MM-DD)")
def version_create(project: str, name: str, description: str, release_date: str) -> None:
    """Create a fix version (milestone) in a project."""
    try:
        client = get_jira_client()
        project_key = resolve_project(project)
        version = client.create_version(project_key, name, description=description, release_date=release_date or None)
        click.echo(f"Created version '{version.get('name', name)}' in {project_key}")

    except SystemExit:
        raise
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        raise SystemExit(1)


@version_group.command(name="delete")
@click.option("--project", "project", "-p", default="", help="Jira project key; defaults to JIRA_PROJECT/JIRA_PROJECT_KEY")
@click.argument("name")
def version_delete(project: str, name: str) -> None:
    """Delete a fix version (milestone) by name."""
    try:
        client = get_jira_client()
        project_key = resolve_project(project)
        deleted = client.delete_version(project_key, name)
        if deleted:
            click.echo(f"Deleted version '{name}' from {project_key}")
        else:
            click.echo(f"No version named '{name}' found in {project_key}", err=True)
            raise SystemExit(1)

    except SystemExit:
        raise
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        raise SystemExit(1)
