"""User resource service functions for the Jira TUI."""

from jira_cli.providers import IssueTrackerProvider


def list_project_users(client: IssueTrackerProvider, project_key: str, max_results: int = 50) -> list[dict]:
    """List users assignable in the current project."""
    return client.list_assignable_users(project_key, max_results=max_results)


def search_project_users(client: IssueTrackerProvider, project_key: str, query: str, max_results: int = 20) -> list[dict]:
    """Search users with the same global-then-project fallback as the CLI."""
    users = client.search_users(query, max_results=max_results)
    if users:
        return users
    return client.find_assignable_users(project_key, query, max_results=max_results)
