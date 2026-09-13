"""Unified GitHub provider supporting both Repository Issues (REST) and Project V2 Boards (GraphQL)."""

from __future__ import annotations

from datetime import timezone
from typing import Optional

from githubkit import GitHub

from jira_cli.models import JiraIssue, JiraIssueField, JiraSearchResult

from .base import ActionDescriptor, FilterDescriptor, ProviderDescriptor, ResourceDescriptor, SortDescriptor
from .github_project import GitHubProjectProvider, parse_project_target

GITHUB_PROVIDER_DESCRIPTOR = ProviderDescriptor(
    name="github",
    query_language="GitHub issue query",
    resources=(
        ResourceDescriptor(
            kind="issues",
            fields=("key", "summary", "status", "assignee", "labels", "milestone", "updated"),
            filters=(
                FilterDescriptor(name="status", field="state"),
                FilterDescriptor(name="assignee", field="assignee", special_values=("me",)),
                FilterDescriptor(name="label", field="labels"),
                FilterDescriptor(name="milestone", field="milestone"),
                FilterDescriptor(name="key", field="number"),
            ),
            sorts=(
                SortDescriptor(name="created", field="created", default_direction="desc"),
                SortDescriptor(name="updated", field="updated", default_direction="desc"),
                SortDescriptor(name="comments", field="comments", default_direction="desc"),
            ),
            actions=(
                ActionDescriptor(name="transition", requires_comment=False),
                ActionDescriptor(name="assign", requires_comment=False),
                ActionDescriptor(name="comment", requires_comment=False),
            ),
        ),
        ResourceDescriptor(
            kind="users",
            fields=("displayName", "emailAddress", "active", "accountId"),
            filters=(FilterDescriptor(name="query", field="query"),),
        ),
        ResourceDescriptor(
            kind="versions",
            fields=("name", "description", "releaseDate", "released", "archived"),
        ),
        ResourceDescriptor(
            kind="labels",
            fields=("name", "color", "description", "issueCount"),
        ),
    ),
)


def is_project_target(target: str) -> bool:
    """Check if target represents a GitHub Project V2 target (owner/number, orgs/owner/projects/number, or digits)."""
    if not target:
        return False
    cleaned = target.strip().strip("/")
    parts = [p for p in cleaned.split("/") if p and p not in ("orgs", "users", "projects")]
    if len(parts) == 2 and parts[1].isdigit():
        return True
    if len(parts) == 1 and parts[0].isdigit():
        return True
    return False


class GitHubProvider:
    """Unified GitHub provider dispatching to Repo REST or Project V2 GraphQL depending on target."""

    dry_run = False

    def __init__(self, target: str, token: str, default_owner: str = ""):
        self.target = target
        self.base_url = f"https://github.com/{target}"
        self._github = GitHub(token)

        if is_project_target(target):
            self._delegate = GitHubProjectProvider(target, token, default_owner=default_owner)
            self._owner = self._delegate.owner
            self._repo_name = ""
        else:
            self._delegate = None
            self.repository = target
            self._owner, self._repo_name = target.split("/", 1)

    def describe(self) -> ProviderDescriptor:
        """Describe GitHub resources and capabilities."""
        if getattr(self, "_delegate", None):
            return self._delegate.describe()
        return GITHUB_PROVIDER_DESCRIPTOR

    def get_issue_url(self, key: str) -> str:
        """Return the web URL for an issue key."""
        if self._delegate:
            return self._delegate.get_issue_url(key)
        number = key.lstrip("#")
        return f"{self.base_url.rstrip('/')}/issues/{number}"

    def search(
        self,
        jql: str,
        fields: Optional[list[str]] = None,
        start_at: int = 0,
        max_results: int = 50,
        expand: Optional[list[str]] = None,
    ) -> JiraSearchResult:
        """Search GitHub issues or project board items."""
        if self._delegate:
            return self._delegate.search(jql, fields, start_at, max_results, expand)

        filters, sort_field, sort_direction = _parse_query(jql)
        state = _github_state(filters.get("status"))
        labels = filters.get("labels")
        params: dict = {"state": state, "per_page": 100}
        if labels:
            params["labels"] = labels
        if filters.get("assignee"):
            params["assignee"] = self._assignee_login(filters["assignee"])
        milestone = _milestone_number(self._github, self._owner, self._repo_name, filters.get("milestone"))
        if milestone:
            params["milestone"] = milestone

        issues = list(
            self._github.rest.paginate(
                self._github.rest.issues.list_for_repo,
                owner=self._owner,
                repo=self._repo_name,
                **params,
            )
        )
        issues = [_issue for _issue in issues if _matches_issue(_issue, filters)]
        issues = _sort_issues(issues, sort_field, sort_direction)
        page = issues[start_at : start_at + max_results]
        return JiraSearchResult(
            issues=[self._to_jira_issue(issue) for issue in page],
            total=len(issues),
            startAt=start_at,
            maxResults=max_results,
        )

    def get_current_user(self) -> dict:
        """Return the authenticated GitHub user."""
        if self._delegate:
            return self._delegate.get_current_user()
        user = self._github.rest.users.get_authenticated().parsed_data
        return _github_user_dict(user)

    def list_assignable_users(self, project_key: str, max_results: int = 50) -> list[dict]:
        """Return repository assignees/collaborators assignable to GitHub issues."""
        if self._delegate:
            return self._delegate.list_assignable_users(project_key, max_results)

        users = list(
            self._github.rest.paginate(
                self._github.rest.issues.list_assignees,
                owner=self._owner,
                repo=self._repo_name,
                per_page=100,
            )
        )
        return [_github_user_dict(user) for user in users[:max_results]]

    def find_assignable_users(self, project_key: str, query: str, max_results: int = 20) -> list[dict]:
        """Search assignees by login/name."""
        if self._delegate:
            return self._delegate.find_assignable_users(project_key, query, max_results)

        query_lower = query.casefold()
        users = [
            user
            for user in self.list_assignable_users(project_key, max_results=100)
            if query_lower in user.get("displayName", "").casefold() or query_lower in user.get("accountId", "").casefold()
        ]
        return users[:max_results]

    def search_users(self, query: str, max_results: int = 20) -> list[dict]:
        """Search repository/board users."""
        return self.find_assignable_users(self.target, query, max_results=max_results)

    def list_versions(self, project_key: str) -> list[dict]:
        """Return repository milestones or empty list."""
        if self._delegate:
            return self._delegate.list_versions(project_key)

        milestones = self._github.rest.issues.list_milestones(
            self._owner, self._repo_name, state="all", per_page=100
        ).parsed_data
        return [_milestone_dict(milestone) for milestone in milestones]

    def list_labels(self, project_key: str) -> list[dict]:
        """Return repository or board labels."""
        if self._delegate:
            return self._delegate.list_labels(project_key)

        labels = self._github.rest.issues.list_labels_for_repo(
            self._owner, self._repo_name, per_page=100
        ).parsed_data
        return [_label_dict(label, self._label_issue_count(label)) for label in labels]

    def _label_issue_count(self, label) -> int:
        """Return open+closed issue count for one label."""
        return sum(
            1
            for _ in self._github.rest.paginate(
                self._github.rest.issues.list_for_repo,
                owner=self._owner,
                repo=self._repo_name,
                state="all",
                labels=label.name,
                per_page=100,
            )
        )

    def get_issue_comments(self, key: str, expand_changelog: bool = False) -> list[dict]:
        """Return comments for a GitHub issue key."""
        if self._delegate:
            return self._delegate.get_issue_comments(key, expand_changelog)

        comments = self._github.rest.paginate(
            self._github.rest.issues.list_comments,
            owner=self._owner,
            repo=self._repo_name,
            issue_number=_issue_number(key),
            per_page=100,
        )
        return [_comment_dict(comment) for comment in comments]

    def add_comment(self, key: str, body: str | dict, use_adf: bool = False) -> dict:
        """Add a comment to an issue."""
        if self._delegate:
            return self._delegate.add_comment(key, body, use_adf)

        num = _issue_number(key)
        text = body if isinstance(body, str) else str(body)
        res = self._github.rest.issues.create_comment(self._owner, self._repo_name, num, body=text).parsed_data
        return {"id": str(res.id), "body": res.body}

    def get_transitions(self, key: str) -> list[dict]:
        """Return available status transitions for an issue."""
        if self._delegate:
            return self._delegate.get_transitions(key)

        # For repo issues, state is open or closed
        return [
            {"id": "closed", "name": "Closed", "to": {"name": "Closed"}},
            {"id": "open", "name": "Open", "to": {"name": "Open"}},
        ]

    def list_transitions(self, key: str) -> list[dict]:
        return self.get_transitions(key)

    def transition_issue(self, key: str, transition_id: str, comment: str | None = None) -> None:
        """Transition issue state (open/closed) in repository."""
        if self._delegate:
            self._delegate.transition_issue(key, transition_id, comment)
            return

        num = _issue_number(key)
        target_state = "closed" if transition_id.casefold() in ("closed", "close", "done") else "open"
        self._github.rest.issues.update(self._owner, self._repo_name, num, state=target_state)
        if comment:
            self.add_comment(key, comment)

    def assign_issue(self, key: str, account_id: str) -> None:
        """Assign issue to user login."""
        if self._delegate:
            self._delegate.assign_issue(key, account_id)
            return

        num = _issue_number(key)
        login = self._resolve_login(account_id)
        self._github.rest.issues.update(self._owner, self._repo_name, num, assignees=[login] if login else [])

    def _resolve_login(self, input_val: str) -> str:
        input_clean = input_val.strip().lstrip("@")
        if not input_clean:
            return ""
        users = self.list_assignable_users(self.repository, max_results=100)
        for u in users:
            if u.get("accountId", "").casefold() == input_clean.casefold():
                return u["accountId"]
        for u in users:
            if u.get("displayName", "").casefold() == input_clean.casefold():
                return u["accountId"]
        return input_clean

    def _to_jira_issue(self, issue) -> JiraIssue:
        labels = [label.name for label in issue.labels]
        assignees = getattr(issue, "assignees", []) or []
        assignee = _github_user_dict(assignees[0]) if assignees else None
        issue_type = _label_value(labels, "type") or "Issue"
        priority = _label_value(labels, "priority") or ""
        return JiraIssue(
            key=f"#{issue.number}",
            fields=JiraIssueField(
                summary=issue.title,
                issuetype={"name": issue_type},
                status={"name": issue.state},
                priority={"name": priority},
                assignee=assignee,
                updated=_datetime_text(issue.updated_at),
                labels=labels,
            ),
        )

    def _assignee_login(self, value: str | None) -> str:
        """Resolve a JQL assignee value to a GitHub login."""
        if not value:
            return ""
        if value == "*":
            return self.get_current_user().get("accountId", "")
        users = self.find_assignable_users(self.repository, value, max_results=1)
        return users[0].get("accountId", "") if users else value


def _parse_query(query: str) -> tuple[dict[str, str], str, str]:
    query_part, _, order_part = query.partition(" ORDER BY ")
    filters: dict[str, str] = {}
    for condition in [part.strip() for part in query_part.split(" AND ")]:
        if not condition or condition.startswith("project ="):
            continue
        if condition == "assignee = currentUser()":
            filters["assignee"] = "*"
            continue
        field, _, raw_value = condition.partition("=")
        field = field.strip()
        value = raw_value.strip().strip('"')
        if field == "key":
            filters["number"] = value
        elif field == "status":
            filters["status"] = value
        elif field == "assignee":
            filters["assignee"] = value
        elif field == "labels":
            filters["labels"] = value
        elif field == "priority":
            filters["priority"] = value
        elif field == "issuetype":
            filters["type"] = value
    if not order_part:
        return filters, "created", "desc"
    parts = order_part.split()
    return filters, parts[0].lower(), parts[1].lower() if len(parts) > 1 else "asc"


def _matches_issue(issue, filters: dict[str, str]) -> bool:
    if filters.get("number") and _issue_number(filters["number"]) != issue.number:
        return False
    labels = [label.name for label in issue.labels]
    if filters.get("priority") and _label_value(labels, "priority") != filters["priority"]:
        return False
    if filters.get("type") and _label_value(labels, "type") != filters["type"]:
        return False
    return True


def _sort_issues(issues: list, field: str, direction: str) -> list:
    reverse = direction == "desc"
    accessors = {
        "created": lambda issue: issue.created_at,
        "updated": lambda issue: issue.updated_at,
        "comments": lambda issue: issue.comments,
    }
    accessor = accessors.get(field)
    return sorted(issues, key=accessor, reverse=reverse) if accessor else issues


def _github_state(status: str | None) -> str:
    if not status:
        return "open"
    normalized = status.casefold()
    if normalized in {"closed", "done"}:
        return "closed"
    if normalized in {"all", "any"}:
        return "all"
    return "open"


def _milestone_number(client: GitHub, owner: str, repo: str, title: str | None) -> str:
    if not title:
        return ""
    milestones = client.rest.issues.list_milestones(owner, repo, state="all", per_page=100).parsed_data
    for milestone in milestones:
        if milestone.title == title:
            return str(milestone.number)
    return ""


def _github_user_dict(user) -> dict:
    name = getattr(user, "name", None) or getattr(user, "login", "")
    login = getattr(user, "login", "")
    return {"accountId": login, "displayName": name, "emailAddress": getattr(user, "email", None) or "-", "active": True}


def _milestone_dict(milestone) -> dict:
    due_on = getattr(milestone, "due_on", None)
    return {
        "id": str(getattr(milestone, "number", "")),
        "name": getattr(milestone, "title", "?"),
        "description": getattr(milestone, "description", "") or "",
        "releaseDate": _date_text(due_on),
        "released": getattr(milestone, "state", "open") == "closed",
        "archived": False,
    }


def _label_dict(label, issue_count: int | str = "") -> dict:
    return {
        "name": getattr(label, "name", "?"),
        "color": getattr(label, "color", "") or "",
        "description": getattr(label, "description", "") or "",
        "issueCount": issue_count,
    }


def _comment_dict(comment) -> dict:
    return {
        "author": {"displayName": getattr(comment.user, "login", "unknown")},
        "created": _datetime_text(getattr(comment, "created_at", None)),
        "body": getattr(comment, "body", ""),
    }


def _label_value(labels: list[str], prefix: str) -> str:
    for label in labels:
        normalized = label.casefold()
        for separator in (":", "/"):
            token = f"{prefix}{separator}"
            if normalized.startswith(token):
                return label[len(token) :]
    return ""


def _issue_number(key: str) -> int:
    value = key.rsplit("#", 1)[-1].strip()
    if value.upper().startswith("GH-"):
        value = value[3:]
    return int(value)


def _datetime_text(value) -> str:
    if not value:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _date_text(value) -> str:
    if not value:
        return "-"
    return value.date().isoformat()
