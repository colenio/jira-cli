"""Click CLI commands."""

import os
import webbrowser
from typing import Optional

import click

from . import __version__
from .client import JiraClient
from .dotenv import DotEnv
from .query import JiraQuery
from .render import JiraRenderer


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(version=__version__)
def cli():
    """Modular Jira CLI — list, search, view, and manage Jira issues."""
    pass


def _get_jira_client(base_url: Optional[str] = None, email: Optional[str] = None, api_token: Optional[str] = None) -> JiraClient:
    """Load Jira credentials from env/dotenv and create client."""
    # Load from .env or local.env first (local.env takes precedence)
    env = DotEnv(verbose=False)
    env.load()

    # Allow override via parameters or env
    base_url = base_url or os.environ.get("JIRA_URL") or os.environ.get("JIRA_BASE_URL")
    email = email or os.environ.get("JIRA_EMAIL") or os.environ.get("JIRA_USER")
    api_token = api_token or os.environ.get("JIRA_API_TOKEN") or os.environ.get("JIRA_TOKEN")

    if not all([base_url, email, api_token]):
        missing = []
        if not base_url:
            missing.append("JIRA_URL or JIRA_BASE_URL")
        if not email:
            missing.append("JIRA_EMAIL or JIRA_USER")
        if not api_token:
            missing.append("JIRA_API_TOKEN or JIRA_TOKEN")
        
        click.echo(f"❌ Missing: {', '.join(missing)}", err=True)
        click.echo("Configure in .env or local.env in CWD or parent directories:", err=True)
        click.echo("  JIRA_URL=https://company.atlassian.net", err=True)
        click.echo("  JIRA_EMAIL=user@example.com", err=True)
        click.echo("  JIRA_API_TOKEN=your_api_token", err=True)
        raise SystemExit(1)

    return JiraClient(base_url=base_url, email=email, api_token=api_token)


def _resolve_project(project: Optional[str]) -> str:
    """Resolve project key from option or env (JIRA_PROJECT/JIRA_PROJECT_KEY)."""
    resolved = project or os.environ.get("JIRA_PROJECT") or os.environ.get("JIRA_PROJECT_KEY")
    if not resolved:
        click.echo("❌ Missing project key. Use --project or set JIRA_PROJECT in local.env/.env", err=True)
        raise SystemExit(1)
    return resolved


@cli.command(name="list")
@click.option("--project", "-p", default="", help="Jira project key (e.g. PROJ); defaults to JIRA_PROJECT/JIRA_PROJECT_KEY")
@click.option("--status", "-s", default="", help="Filter by status (e.g. 'To Do')")
@click.option("--assignee", "-a", default="", help="Filter by assignee")
@click.option("--label", "-l", default="", help="Filter by label")
@click.option("--jql", "-j", default="", help="Additional JQL conditions (AND appended)")
@click.option("--max-results", "-m", type=int, default=50, show_default=True, help="Max issues to return")
@click.option("--format", "-f", type=click.Choice(["table", "json", "csv", "md"]), default="table", help="Output format")
def list_issues(project: str, status: str, assignee: str, label: str, jql: str, max_results: int, format: str):
    """List issues in a project with optional filters."""
    try:
        client = _get_jira_client()
        query = JiraQuery(client)
        renderer = JiraRenderer()
        project_key = _resolve_project(project)

        rows = query.search_project(
            project_key=project_key,
            status=status or None,
            assignee=assignee or None,
            label=label or None,
            jql_extra=jql or None,
            max_results=max_results,
        )

        if format == "table":
            renderer.table(rows, title=f"Issues in {project_key}")
        elif format == "json":
            output = renderer.json(rows)
            renderer.print(output)
        elif format == "csv":
            output = renderer.csv(rows)
            renderer.print(output)
        elif format == "md":
            output = renderer.markdown(rows)
            renderer.print(output)

    except SystemExit:
        raise
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        raise SystemExit(1)


@cli.command(name="search")
@click.argument("jql")
@click.option("--max-results", "-m", type=int, default=50, show_default=True)
@click.option("--format", "-f", type=click.Choice(["table", "json", "csv", "md"]), default="table")
def search(jql: str, max_results: int, format: str):
    """Search issues using custom JQL."""
    try:
        client = _get_jira_client()
        query = JiraQuery(client)
        renderer = JiraRenderer()

        rows = query.search_custom_jql(jql, max_results=max_results)

        if format == "table":
            renderer.table(rows, title="Search Results")
        elif format == "json":
            output = renderer.json(rows)
            renderer.print(output)
        elif format == "csv":
            output = renderer.csv(rows)
            renderer.print(output)
        elif format == "md":
            output = renderer.markdown(rows)
            renderer.print(output)

    except SystemExit:
        raise
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        raise SystemExit(1)


@cli.command(name="find")
@click.option("--project", "-p", default="", help="Jira project key; defaults to JIRA_PROJECT/JIRA_PROJECT_KEY")
@click.argument("text")
@click.option("--max-results", "-m", type=int, default=50, show_default=True)
@click.option("--format", "-f", type=click.Choice(["table", "json", "csv"]), default="table")
def find(project: str, text: str, max_results: int, format: str):
    """Find issues by text in summary/description."""
    try:
        client = _get_jira_client()
        query = JiraQuery(client)
        renderer = JiraRenderer()
        project_key = _resolve_project(project)

        rows = query.find_by_text(project_key, text, max_results=max_results)

        if format == "table":
            renderer.table(rows, title=f"Search for '{text}' in {project_key}")
        elif format == "json":
            output = renderer.json(rows)
            renderer.print(output)
        elif format == "csv":
            output = renderer.csv(rows)
            renderer.print(output)

    except SystemExit:
        raise
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        raise SystemExit(1)


@cli.command(name="view")
@click.argument("key")
@click.option("--comments", "-c", is_flag=True, help="Include issue comments")
@click.option("--web", "-w", is_flag=True, help="Show issue URL and open in browser")
def view(key: str, comments: bool, web: bool):
    """View issue details."""
    try:
        client = _get_jira_client()
        issue = client.get_issue(
            key,
            fields=["key", "summary", "description", "status", "priority", "assignee", "labels", "comment"],
        )
        issue_url = f"{client.base_url.rstrip('/')}/browse/{issue['key']}"

        fields = issue.get("fields", {})
        
        click.echo(f"\n📌 {issue['key']}: {fields.get('summary', 'N/A')}\n")
        click.echo(f"  Status:      {fields.get('status', {}).get('name', 'N/A')}")
        click.echo(f"  Priority:    {fields.get('priority', {}).get('name', 'N/A')}")
        assignee = fields.get("assignee")
        click.echo(f"  Assignee:    {assignee.get('displayName', 'Unassigned') if assignee else 'Unassigned'}")
        labels = fields.get("labels", [])
        click.echo(f"  Labels:      {', '.join(labels) if labels else 'None'}")
        
        description = fields.get("description")
        if description:
            click.echo(f"\n📝 Description:")
            if isinstance(description, dict):  # Rich text format
                click.echo("  (Rich text format)")
            else:
                click.echo(f"  {description}")

        if comments:
            comments_list = fields.get("comment", {}).get("comments", [])
            if comments_list:
                click.echo(f"\n💬 Comments ({len(comments_list)}):")
                for c in comments_list:
                    author = c.get("author", {}).get("displayName", "Unknown")
                    body = c.get("body", {})
                    if isinstance(body, dict):
                        click.echo(f"  @{author}: (Rich text)")
                    else:
                        click.echo(f"  @{author}: {body}")
            else:
                click.echo("\n💬 No comments")

        if web and issue_url:
            click.echo(f"\n🌐 URL: {issue_url}")
            opened = webbrowser.open(issue_url)
            if not opened:
                click.echo("⚠️ Browser could not be opened automatically")

        click.echo()

    except SystemExit:
        raise
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        raise SystemExit(1)


@cli.command(name="assign")
@click.argument("key")
@click.argument("assignee")
@click.option("--comment", "-c", default="", help="Optional transition comment")
def assign_issue(key: str, assignee: str, comment: str):
    """Assign issue to user."""
    try:
        client = _get_jira_client()
        client.assign_issue(key, assignee)
        click.echo(f"✅ Assigned {key} to {assignee}")

    except SystemExit:
        raise
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        raise SystemExit(1)


@cli.command(name="transition")
@click.argument("key")
@click.argument("transition_id")
@click.option("--comment", "-c", default="", help="Optional transition comment")
def transition(key: str, transition_id: str, comment: str):
    """Transition issue to new status."""
    try:
        client = _get_jira_client()
        client.transition_issue(key, transition_id, comment=comment or None)
        click.echo(f"✅ Transitioned {key} to {transition_id}")

    except SystemExit:
        raise
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        raise SystemExit(1)


@cli.command(name="tui")
@click.option("--project", "-p", default="", help="Jira project key; defaults to JIRA_PROJECT/JIRA_PROJECT_KEY")
def launch_tui(project: str):
    """Launch interactive TUI (Terminal User Interface) for Jira issue management."""
    try:
        from .tui.app import run_tui
        
        client = _get_jira_client()
        project_key = _resolve_project(project)
        run_tui(client, project_key)

    except ImportError:
        click.echo("❌ TUI module could not be loaded (installation may be incomplete).", err=True)
        click.echo("Run: uv sync", err=True)
        raise SystemExit(1)
    except SystemExit:
        raise
    except Exception as e:
        click.echo(f"❌ Error: {e}", err=True)
        raise SystemExit(1)


def main():
    """Main entry point."""
    cli()


if __name__ == "__main__":
    main()
