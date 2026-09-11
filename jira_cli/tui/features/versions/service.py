"""Version resource service functions for the Jira TUI."""

from jira_cli.client import JiraClient


def list_project_versions(client: JiraClient, project_key: str) -> list[dict]:
    """List fix versions/milestones in the current project."""
    return client.list_versions(project_key)
