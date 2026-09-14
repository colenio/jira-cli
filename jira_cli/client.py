"""Jira API client."""

import json
from typing import Any, Optional

from jira import JIRA

from .adf import markdown_to_adf_document
from .models import JiraSearchResult


class JiraClient:
    """Client wrapper around the official jira Python library."""

    def __init__(self, base_url: str, email: str, api_token: str, dry_run: bool = False, timeout: int = 30):
        """
        Initialize Jira client.

        Args:
            base_url: Jira instance URL (e.g. https://company.atlassian.net)
            email: Jira user email
            api_token: Jira API token (from Account Settings → Security)
            dry_run: If True, only print requests without executing
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.email = email
        self.api_token = api_token
        self.dry_run = dry_run
        self.timeout = timeout
        self._jira = JIRA(
            server=self.base_url,
            basic_auth=(self.email, self.api_token),
            options={"rest_api_version": "3"},
            timeout=self.timeout,
        )

    def get_issue_url(self, key: str) -> str:
        """Return the web URL for an issue key."""
        return f"{self.base_url.rstrip('/')}/browse/{key}"

    def search(
        self,
        jql: str,
        fields: Optional[list[str]] = None,
        start_at: int = 0,
        max_results: int = 50,
        expand: Optional[list[str]] = None,
    ) -> JiraSearchResult:
        """
        Search issues using JQL via official client.

        Args:
            jql: JQL query string
            fields: List of fields to return (e.g. ['key', 'summary', 'status'])
            start_at: Start index for pagination
            max_results: Max issues to return (max 100 for API limit)
            expand: List of fields to expand (e.g. 'changelog')

        Returns:
            JiraSearchResult with issues list
        """
        if self.dry_run:
            print(f"[dry-run] POST /search/jql | JQL={jql} | start_at={start_at} | max_results={max_results}")
            return JiraSearchResult(issues=[], total=0)

        raw = self._jira.search_issues(
            jql_str=jql,
            startAt=start_at,
            maxResults=max_results,
            fields=fields if fields else None,
            expand=",".join(expand) if expand else None,
            json_result=True,
            use_post=True,
        )

        return JiraSearchResult(**raw)

    def get_issue(self, key: str, fields: Optional[list[str]] = None, expand: Optional[list[str]] = None) -> dict:
        """
        Fetch single issue by key.

        Args:
            key: Issue key (e.g. 'JIRA-123')
            fields: List of fields to return
            expand: List of fields to expand

        Returns:
            Issue dict
        """
        if self.dry_run:
            print(f"[dry-run] GET /issues/{key}")
            return {}

        issue = self._jira.issue(
            key,
            fields=fields if fields else None,
            expand=",".join(expand) if expand else None,
        )
        return issue.raw

    def get_current_user(self) -> dict:
        """
        Fetch the authenticated account's user info (e.g. for 'assignee=me' resolution).

        Returns:
            Dict with at least 'displayName' if available, else {}
        """
        if self.dry_run:
            return {}

        return self._jira.myself()

    def _search_assignable_users(self, project_key: str, query: Optional[str], max_results: int) -> list[dict]:
        """
        Call GET /user/assignable/multiProjectSearch directly with the 'query' param.

        The jira-python library's own `search_assignable_users_for_projects()` sends the
        deprecated 'username' param instead, which modern Jira Cloud instances reject with
        HTTP 400 ("not supported in GDPR strict mode").
        """
        params: dict[str, Any] = {"projectKeys": project_key, "maxResults": max_results}
        if query:
            params["query"] = query
        return self._jira._get_json("user/assignable/multiProjectSearch", params=params)

    def find_assignable_users(self, project_key: str, query: str, max_results: int = 20) -> list[dict]:
        """
        Search assignable users for a project by partial name/email, server-side.

        Unlike matching against already-loaded issues, this searches Jira's full user
        directory for the project, so it isn't limited to whatever issues happen to be
        currently loaded in the TUI (e.g. for the ':assignee=<name>' quick filter).

        Args:
            project_key: Jira project key
            query: Partial display name or email to search for
            max_results: Max users to return

        Returns:
            List of user dicts (accountId, displayName, emailAddress, active, ...)
        """
        if self.dry_run or not query:
            return []

        return self._search_assignable_users(project_key, query, max_results)

    def list_assignable_users(self, project_key: str, max_results: int = 50) -> list[dict]:
        """
        List all users assignable to issues in a project (e.g. project members).

        Args:
            project_key: Jira project key
            max_results: Max users to return

        Returns:
            List of user dicts (accountId, displayName, emailAddress, active, ...)
        """
        if self.dry_run:
            return []

        return self._search_assignable_users(project_key, None, max_results)

    def list_projects(self) -> list[dict]:
        """
        List projects accessible to the authenticated account.

        Returns:
            List of dicts with at least 'key' and 'name'
        """
        if self.dry_run:
            return []

        return [p.raw for p in self._jira.projects()]

    def get_project(self, key: str) -> dict:
        """
        Fetch details for a single project.

        Args:
            key: Jira project key

        Returns:
            Project dict (key, name, lead, projectTypeKey, description, ...)
        """
        if self.dry_run:
            return {}

        return self._jira.project(key).raw

    def list_versions(self, project_key: str) -> list[dict]:
        """
        List fix versions (milestones) for a project.

        Args:
            project_key: Jira project key

        Returns:
            List of dicts (id, name, description, releaseDate, released, archived, ...)
        """
        if self.dry_run:
            return []

        return [v.raw for v in self._jira.project_versions(project_key)]

    def list_labels(self, project_key: str) -> list[dict]:
        """List labels used by issues in a project."""
        if self.dry_run:
            return []

        raw = self._jira.search_issues(
            jql_str=f"project = {project_key}",
            maxResults=100,
            fields=["labels"],
            json_result=True,
            use_post=True,
        )
        counts: dict[str, int] = {}
        for issue in raw.get("issues", []):
            for label in issue.get("fields", {}).get("labels", []) or []:
                counts[label] = counts.get(label, 0) + 1
        return [{"name": name, "issueCount": count} for name, count in sorted(counts.items())]

    def create_version(
        self, project_key: str, name: str, description: str = "", release_date: Optional[str] = None
    ) -> dict:
        """
        Create a fix version (milestone) in a project.

        Args:
            project_key: Jira project key
            name: Version name
            description: Optional description
            release_date: Optional release date (YYYY-MM-DD)

        Returns:
            Created version dict
        """
        if self.dry_run:
            print(f"[dry-run] POST /version | project={project_key} | name={name!r}")
            return {"name": name}

        version = self._jira.create_version(
            name=name, project=project_key, description=description or None, releaseDate=release_date
        )
        return version.raw

    def delete_version(self, project_key: str, name: str) -> bool:
        """
        Delete a fix version (milestone) by name.

        Args:
            project_key: Jira project key
            name: Version name to delete

        Returns:
            True if a matching version was found and deleted, False otherwise
        """
        if self.dry_run:
            print(f"[dry-run] DELETE version | project={project_key} | name={name!r}")
            return True

        for version in self._jira.project_versions(project_key):
            if version.name == name:
                version.delete()
                return True
        return False

    def search_users(self, query: str, max_results: int = 20) -> list[dict]:
        """
        Search Jira users globally (not project-scoped) by name/email.

        Args:
            query: Partial display name or email to search for
            max_results: Max users to return

        Returns:
            List of user dicts (accountId, displayName, emailAddress, active, ...)
        """
        if self.dry_run or not query:
            return []

        users = self._jira.search_users(query=query, maxResults=max_results)
        return [u.raw for u in users]

    def get_issue_comments(self, key: str, expand_changelog: bool = False) -> list[dict]:
        """
        Fetch comments for an issue.

        Args:
            key: Issue key
            expand_changelog: Include changelog details

        Returns:
            List of comment dicts
        """
        if self.dry_run:
            print(f"[dry-run] GET /issues/{key}/comments")
            return []

        comments = self._jira.comments(key)
        return [c.raw for c in comments]

    def transition_issue(self, key: str, transition_id: str, comment: Optional[str] = None) -> None:
        """
        Transition issue to new status.

        Args:
            key: Issue key
            transition_id: Transition ID (e.g. 'In Progress', 'Done')
            comment: Optional comment to add
        """
        if self.dry_run:
            print(f"[dry-run] POST /issues/{key}/transitions | transition={transition_id}")
            return

        self._jira.transition_issue(key, transition_id, comment=comment or None)

    def get_transitions(self, key: str) -> list[dict]:
        """
        Fetch available transitions for an issue.

        Args:
            key: Issue key

        Returns:
            List of transition dicts (id, name, to, ...)
        """
        if self.dry_run:
            print(f"[dry-run] GET /issues/{key}/transitions")
            return []

        return self._jira.transitions(key)

    def assign_issue(self, key: str, assignee_key: str) -> None:
        """
        Assign issue to user.

        Args:
            key: Issue key
            assignee_key: User key or email
        """
        if self.dry_run:
            print(f"[dry-run] PUT /issues/{key} | assignee={assignee_key}")
            return

        self._jira.assign_issue(key, assignee_key)

    def create_issue(
        self,
        project_key: str,
        title: str,
        body: str | dict[str, Any] | None = None,
        issue_type: str = "Task",
        labels: Optional[list[str]] = None,
        assignee: Optional[str] = None,
        priority: Optional[str] = None,
        parent: Optional[str] = None,
    ) -> dict:
        """Create a Jira issue and return its raw payload.

        Args:
            project_key: Jira project key (e.g. ANN)
            title: Issue summary/title
            body: Description text or ADF document
            issue_type: Jira issue type name (e.g. Task, Story, Bug)
            labels: Optional issue labels
            assignee: Optional assignee (email/accountId depending on Jira config)
            priority: Optional priority name (e.g. High)
            parent: Optional parent issue key
        """
        if self.dry_run:
            print(
                f"[dry-run] POST /issues | project={project_key} | type={issue_type} | "
                f"title={title!r}"
            )
            return {"key": "DRY-0"}

        fields: dict[str, Any] = {
            "project": {"key": project_key},
            "summary": title,
            "issuetype": {"name": issue_type},
        }

        if body is not None:
            fields["description"] = body
        if labels:
            fields["labels"] = labels
        if priority:
            fields["priority"] = {"name": priority}
        if parent:
            fields["parent"] = {"key": parent}

        issue = self._jira.create_issue(fields=fields)

        # Assign after creation because assignment semantics can vary by Jira setup.
        if assignee:
            self._jira.assign_issue(issue.key, assignee)

        return issue.raw

    def add_comment(self, key: str, comment: str | dict[str, Any], use_adf: bool = False) -> None:
        """
        Add comment to an issue.

        Args:
            key: Issue key
            comment: Comment text or ADF document
            use_adf: If True, send raw ADF JSON body
        """
        if self.dry_run:
            mode = "adf" if use_adf else "plain"
            print(f"[dry-run] POST /issues/{key}/comments | mode={mode}")
            return

        if use_adf:
            if not isinstance(comment, dict):
                raise ValueError("ADF comment must be a JSON object")
            url = f"{self.base_url}/rest/api/3/issue/{key}/comment"
            response = self._jira._session.post(url, json={"body": comment})
            response.raise_for_status()
            return

        adf_comment = markdown_to_adf_document(comment if isinstance(comment, str) else json.dumps(comment, ensure_ascii=False))
        url = f"{self.base_url}/rest/api/3/issue/{key}/comment"
        response = self._jira._session.post(url, json={"body": adf_comment})
        response.raise_for_status()

    def update_issue(self, key: str, fields: dict[str, Any]) -> None:
        """Update issue fields.

        Args:
            key: Issue key
            fields: Jira fields payload to update
        """
        if self.dry_run:
            print(f"[dry-run] PUT /issues/{key} | fields={list(fields.keys())}")
            return

        issue = self._jira.issue(key)
        issue.update(fields=fields)
