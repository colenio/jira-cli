"""User lookup commands."""

import os

import click

from jira_cli.commands.common import OrderedGroup, get_jira_client, resolve_project
from jira_cli.render import JiraRenderer


@click.group(name="user", cls=OrderedGroup)
def user_group() -> None:
    """Look up Jira users."""


@user_group.command(name="me")
def user_me() -> None:
    """Show the authenticated account's user info."""
    try:
        client = get_jira_client()
        user = client.get_current_user()
        if not user:
            click.echo("Could not fetch current user (dry-run mode or API error)")
            return

        click.echo(f"\n{user.get('displayName', '?')}\n")
        click.echo(f"  Email:      {user.get('emailAddress', '-')}")
        click.echo(f"  Account ID: {user.get('accountId', '-')}")
        click.echo()

    except SystemExit:
        raise
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        raise SystemExit(1)


@user_group.command(name="list")
@click.option("--project", "project", "-p", default="", help="Jira project key; defaults to JIRA_PROJECT/JIRA_PROJECT_KEY")
@click.option("--max-results", "max_results", "-m", type=int, default=50, show_default=True)
def user_list(project: str, max_results: int) -> None:
    """List all users assignable to issues in a project (e.g. project members)."""
    try:
        client = get_jira_client()
        renderer = JiraRenderer()
        project_key = resolve_project(project)
        users = client.list_assignable_users(project_key, max_results=max_results)

        renderer.users_table(users, title=f"Assignable users in {project_key}")

    except SystemExit:
        raise
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        raise SystemExit(1)


@user_group.command(name="search")
@click.argument("query")
@click.option(
    "--project",
    "project",
    "-p",
    default="",
    help="Project key for the assignable-users fallback; defaults to JIRA_PROJECT/JIRA_PROJECT_KEY",
)
@click.option("--max-results", "max_results", "-m", type=int, default=20, show_default=True)
def user_search(query: str, project: str, max_results: int) -> None:
    """Search Jira users globally by partial name or email.

    Jira Cloud's global user search silently returns no results if the API token's
    account lacks the "Browse users and groups" permission (common in locked-down
    orgs) - no error, just an empty list. When that happens, this falls back to the
    project-scoped assignable-users search, which only needs "Browse Projects".
    """
    try:
        client = get_jira_client()
        renderer = JiraRenderer()
        users = client.search_users(query, max_results=max_results)

        if not users:
            project_key = project or os.environ.get("JIRA_PROJECT") or os.environ.get("JIRA_PROJECT_KEY")
            if project_key:
                users = client.find_assignable_users(project_key, query, max_results=max_results)

        renderer.users_table(users, title=f"Users matching '{query}'")

    except SystemExit:
        raise
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        raise SystemExit(1)
