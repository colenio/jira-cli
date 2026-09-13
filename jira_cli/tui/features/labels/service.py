"""Label resource service functions for the TUI."""

from jira_cli.providers import IssueTrackerProvider


def list_project_labels(client: IssueTrackerProvider, project_key: str) -> list[dict]:
    """List labels/tags in the current provider context."""
    return client.list_labels(project_key)
