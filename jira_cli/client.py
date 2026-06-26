"""Jira API client."""

import json
from typing import Any, Optional

from jira import JIRA

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

        if isinstance(comment, dict):
            comment = json.dumps(comment, ensure_ascii=False)
        self._jira.add_comment(key, comment)
