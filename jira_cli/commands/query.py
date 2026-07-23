"""Read/query related Jira commands."""

import webbrowser

import click

from jira_cli.commands.common import get_jira_client, resolve_project
from jira_cli.query import JiraQuery
from jira_cli.render import JiraRenderer


@click.command(name="list")
@click.option(
    "--project",
    "project",
    "-p",
    default="",
    help="Jira project key (e.g. PROJ); defaults to JIRA_PROJECT/JIRA_PROJECT_KEY",
)
@click.option("--status", "status", "-s", default="", help="Filter by status (e.g. 'To Do')")
@click.option("--assignee", "assignee", "-a", default="", help="Filter by assignee")
@click.option("--label", "label", "-l", default="", help="Filter by label")
@click.option("--jql", "jql", "-j", default="", help="Additional JQL conditions (AND appended)")
@click.option("--max-results", "max_results", "-m", type=int, default=50, show_default=True, help="Max issues to return")
@click.option(
    "--format",
    "format_name",
    "-f",
    type=click.Choice(["table", "json", "csv", "md"]),
    default="table",
    help="Output format",
)
def list_issues(project: str, status: str, assignee: str, label: str, jql: str, max_results: int, format_name: str) -> None:
    """List issues in a project with optional filters."""
    try:
        client = get_jira_client()
        query = JiraQuery(client)
        renderer = JiraRenderer()
        project_key = resolve_project(project)

        rows = query.search_project(
            project_key=project_key,
            status=status or None,
            assignee=assignee or None,
            label=label or None,
            jql_extra=jql or None,
            max_results=max_results,
        )

        if format_name == "table":
            renderer.table(rows, title=f"Issues in {project_key}")
        elif format_name == "json":
            renderer.print(renderer.json(rows))
        elif format_name == "csv":
            renderer.print(renderer.csv(rows))
        elif format_name == "md":
            renderer.print(renderer.markdown(rows))

    except SystemExit:
        raise
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        raise SystemExit(1)


@click.command(name="search")
@click.argument("jql")
@click.option("--max-results", "max_results", "-m", type=int, default=50, show_default=True)
@click.option("--format", "format_name", "-f", type=click.Choice(["table", "json", "csv", "md"]), default="table")
def search_issues(jql: str, max_results: int, format_name: str) -> None:
    """Search issues using custom JQL."""
    try:
        client = get_jira_client()
        query = JiraQuery(client)
        renderer = JiraRenderer()

        rows = query.search_custom_jql(jql, max_results=max_results)

        if format_name == "table":
            renderer.table(rows, title="Search Results")
        elif format_name == "json":
            renderer.print(renderer.json(rows))
        elif format_name == "csv":
            renderer.print(renderer.csv(rows))
        elif format_name == "md":
            renderer.print(renderer.markdown(rows))

    except SystemExit:
        raise
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        raise SystemExit(1)


@click.command(name="find")
@click.option("--project", "project", "-p", default="", help="Jira project key; defaults to JIRA_PROJECT/JIRA_PROJECT_KEY")
@click.argument("text")
@click.option("--max-results", "max_results", "-m", type=int, default=50, show_default=True)
@click.option("--format", "format_name", "-f", type=click.Choice(["table", "json", "csv"]), default="table")
def find_issues(project: str, text: str, max_results: int, format_name: str) -> None:
    """Find issues by text in summary/description."""
    try:
        client = get_jira_client()
        query = JiraQuery(client)
        renderer = JiraRenderer()
        project_key = resolve_project(project)

        rows = query.find_by_text(project_key, text, max_results=max_results)

        if format_name == "table":
            renderer.table(rows, title=f"Search for '{text}' in {project_key}")
        elif format_name == "json":
            renderer.print(renderer.json(rows))
        elif format_name == "csv":
            renderer.print(renderer.csv(rows))

    except SystemExit:
        raise
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        raise SystemExit(1)


@click.command(name="view")
@click.argument("key")
@click.option("--comments", "comments", "-c", is_flag=True, help="Include issue comments")
@click.option("--web", "web", "-w", is_flag=True, help="Show issue URL and open in browser")
def view_issue(key: str, comments: bool, web: bool) -> None:
    """View issue details."""
    try:
        client = get_jira_client()
        issue = client.get_issue(
            key,
            fields=["key", "summary", "description", "status", "priority", "assignee", "labels", "comment"],
        )
        issue_url = f"{client.base_url.rstrip('/')}/browse/{issue['key']}"

        fields = issue.get("fields", {})
        click.echo(f"\n{issue['key']}: {fields.get('summary', 'N/A')}\n")
        click.echo(f"  Status:      {fields.get('status', {}).get('name', 'N/A')}")
        click.echo(f"  Priority:    {fields.get('priority', {}).get('name', 'N/A')}")
        assignee = fields.get("assignee")
        click.echo(f"  Assignee:    {assignee.get('displayName', 'Unassigned') if assignee else 'Unassigned'}")
        labels = fields.get("labels", [])
        click.echo(f"  Labels:      {', '.join(labels) if labels else 'None'}")

        description = fields.get("description")
        if description:
            click.echo("\nDescription:")
            if isinstance(description, dict):
                click.echo("  (Rich text format)")
            else:
                click.echo(f"  {description}")

        if comments:
            comments_list = fields.get("comment", {}).get("comments", [])
            if comments_list:
                click.echo(f"\nComments ({len(comments_list)}):")
                for comment in comments_list:
                    author = comment.get("author", {}).get("displayName", "Unknown")
                    body = comment.get("body", {})
                    if isinstance(body, dict):
                        click.echo(f"  @{author}: (Rich text)")
                    else:
                        click.echo(f"  @{author}: {body}")
            else:
                click.echo("\nNo comments")

        if web and issue_url:
            click.echo(f"\nURL: {issue_url}")
            opened = webbrowser.open(issue_url)
            if not opened:
                click.echo("Browser could not be opened automatically")

        click.echo()

    except SystemExit:
        raise
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        raise SystemExit(1)
