"""Read/query related Jira commands."""

import webbrowser

import click

from jira_cli.commands.common import get_jira_client, resolve_project
from jira_cli.query import JiraQuery
from jira_cli.render import JiraRenderer, adf_to_text


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
@click.option("--type", "issue_type", "-t", default="", help="Filter by issue type (e.g. 'Bug', 'Story')")
@click.option("--priority", "priority", default="", help="Filter by priority (e.g. 'High')")
@click.option("--order", "order_by", "-o", default="", help="Order by field, optionally with asc/desc")
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
def list_issues(
    project: str,
    status: str,
    assignee: str,
    label: str,
    issue_type: str,
    priority: str,
    order_by: str,
    jql: str,
    max_results: int,
    format_name: str,
) -> None:
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
            issue_type=issue_type or None,
            priority=priority or None,
            order_by=order_by or None,
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
            text = adf_to_text(description) if isinstance(description, dict) else str(description)
            for line in text.rstrip("\n").splitlines() or [""]:
                click.echo(f"  {line}")

        if comments:
            comments_list = fields.get("comment", {}).get("comments", [])
            if comments_list:
                click.echo(f"\nComments ({len(comments_list)}):")
                for comment in comments_list:
                    author = comment.get("author", {}).get("displayName", "Unknown")
                    body = comment.get("body", {})
                    text = adf_to_text(body) if isinstance(body, dict) else str(body)
                    click.echo(f"  @{author}: {text.strip()}")
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


@click.command(name="children")
@click.argument("key")
@click.option("--max-results", "max_results", "-m", type=int, default=50, show_default=True)
@click.option("--format", "format_name", "-f", type=click.Choice(["table", "json", "csv", "md"]), default="table")
def children_issues(key: str, max_results: int, format_name: str) -> None:
    """List child issues of KEY (Epic -> Story/Task, Story -> Sub-task) via Jira's 'parent' field."""
    try:
        client = get_jira_client()
        query = JiraQuery(client)
        renderer = JiraRenderer()

        rows = query.find_children(key, max_results=max_results)

        if format_name == "table":
            renderer.table(rows, title=f"Children of {key}")
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


@click.command(name="overdue")
@click.option("--project", "project", "-p", default="", help="Jira project key; defaults to JIRA_PROJECT/JIRA_PROJECT_KEY")
@click.option("--mine", "mine", is_flag=True, help="Only issues assigned to the authenticated account")
@click.option("--max-results", "max_results", "-m", type=int, default=50, show_default=True)
@click.option("--format", "format_name", "-f", type=click.Choice(["table", "json", "csv", "md"]), default="table")
def overdue_issues(project: str, mine: bool, max_results: int, format_name: str) -> None:
    """List overdue issues in a project (due date passed, not in a Done-category status)."""
    try:
        client = get_jira_client()
        query = JiraQuery(client)
        renderer = JiraRenderer()
        project_key = resolve_project(project)

        rows = query.find_overdue(project_key, mine=mine, max_results=max_results)

        title = f"Overdue issues in {project_key}" + (" (mine)" if mine else "")
        if format_name == "table":
            renderer.table(rows, title=title)
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
