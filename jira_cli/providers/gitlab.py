"""GitLab project provider for issues, milestones, and the shared TUI."""

from __future__ import annotations

import os
import re
from datetime import date

import gitlab

from jira_cli.models import JiraIssue, JiraIssueField, JiraSearchResult

from .base import ActionDescriptor, FilterDescriptor, ProviderDescriptor, ResourceDescriptor, SortDescriptor

GITLAB_PROVIDER_DESCRIPTOR = ProviderDescriptor(
    name="gitlab",
    query_language="GitLab issue filters",
    supports_board=False,
    token_env="GITLAB_TOKEN",
    token_url="https://gitlab.com/-/user_settings/personal_access_tokens",
    resources=(
        ResourceDescriptor(
            kind="issues",
            fields=("key", "summary", "status", "assignee", "reporter", "labels", "milestone", "updated"),
            filters=(
                FilterDescriptor(name="status", field="state"),
                FilterDescriptor(name="assignee", field="assignee_username", special_values=("me", "none")),
                FilterDescriptor(name="label", field="labels"),
                FilterDescriptor(name="milestone", field="milestone"),
                FilterDescriptor(name="key", field="iid"),
            ),
            sorts=(SortDescriptor(name="created", field="created_at", default_direction="desc"),
                   SortDescriptor(name="updated", field="updated_at", default_direction="desc")),
            actions=(ActionDescriptor(name="create"), ActionDescriptor(name="transition"),
                     ActionDescriptor(name="assign"), ActionDescriptor(name="comment")),
        ),
        ResourceDescriptor(kind="users", fields=("displayName", "emailAddress", "active", "accountId")),
        ResourceDescriptor(
            kind="versions",
            fields=("name", "description", "startDate", "releaseDate", "released", "archived"),
            actions=(ActionDescriptor(name="create"), ActionDescriptor(name="edit"), ActionDescriptor(name="delete")),
        ),
        ResourceDescriptor(
            kind="labels",
            fields=("name", "color", "description", "issueCount"),
            actions=(ActionDescriptor(name="create"), ActionDescriptor(name="edit"), ActionDescriptor(name="delete")),
        ),
    ),
)


class GitLabProvider:
    """Adapt a GitLab project to the shared issue tracker interface."""

    dry_run = False

    def __init__(self, target: str, token: str, url: str | None = None, admin_token: str | None = None):
        self.target = target.strip("/")
        self.base_url = (url or os.environ.get("GITLAB_URL") or "https://gitlab.com").rstrip("/")
        self._gitlab = gitlab.Gitlab(self.base_url, private_token=token)
        self._gitlab_admin = gitlab.Gitlab(self.base_url, private_token=admin_token) if admin_token else None
        self._admin_email_cache: dict[str, str] = {}
        self.project = self._gitlab.projects.get(self.target)
        self.project_key = str(getattr(self.project, "path_with_namespace", self.target))

    def describe(self) -> ProviderDescriptor:
        return GITLAB_PROVIDER_DESCRIPTOR

    def list_resource(self, kind: str, project_key: str) -> list[dict]:
        raise ValueError(f"GitLab provider does not expose resource '{kind}'")

    def get_issue_url(self, key: str) -> str:
        issue = self._get_issue(key)
        return str(getattr(issue, "web_url", f"{self.base_url}/{self.project_key}/-/issues/{self._iid(key)}"))

    def search(self, jql: str, fields=None, start_at: int = 0, max_results: int = 50, expand=None) -> JiraSearchResult:
        filters, order_field, direction = _parse_jql(jql)
        params: dict = {"state": "all", "order_by": order_field, "sort": direction}
        if filters.get("labels"):
            params["labels"] = filters["labels"]
        if filters.get("milestone"):
            params["milestone"] = filters["milestone"]
        if filters.get("assignee"):
            assignee = filters["assignee"]
            if assignee.casefold() == "me":
                assignee = self.get_current_user().get("accountId", "")
            if assignee.casefold() == "none":
                params["assignee_id"] = "None"
            else:
                params["assignee_username"] = assignee

        issues = self.project.issues.list(all=True, per_page=100, **params)
        matching = [issue for issue in issues if _matches(issue, filters, self.project_key)]
        page = matching[start_at : start_at + max_results]
        return JiraSearchResult(
            issues=[self._to_jira_issue(issue) for issue in page],
            total=len(matching),
            startAt=start_at,
            maxResults=max_results,
        )

    def get_current_user(self) -> dict:
        self._gitlab.auth()
        user = self._gitlab.user
        return _user_dict(user, include_private_email=True)

    def list_assignable_users(self, project_key: str, max_results: int = 50) -> list[dict]:
        members = self.project.members_all.list(all=True, per_page=100)
        users = [_user_dict(member) for member in members[:max_results]]
        current_user = self.get_current_user()
        for user in users:
            if user["accountId"] == current_user["accountId"] and current_user["emailAddress"] != "-":
                user["emailAddress"] = current_user["emailAddress"]
            elif self._gitlab_admin:
                private_email = self._private_member_email(user["accountId"])
                if private_email:
                    user["emailAddress"] = private_email
        return users

    def _private_member_email(self, user_id: str) -> str:
        """Read a private member email only when the optional admin token is configured."""
        if user_id not in self._admin_email_cache:
            try:
                user = self._gitlab_admin.users.get(int(user_id))
                self._admin_email_cache[user_id] = str(getattr(user, "email", "") or "")
            except Exception:
                self._admin_email_cache[user_id] = ""
        return self._admin_email_cache[user_id]

    def find_assignable_users(self, project_key: str, query: str, max_results: int = 20) -> list[dict]:
        normalized = query.casefold()
        return [
            user for user in self.list_assignable_users(project_key, max_results=1000)
            if normalized in user["displayName"].casefold() or normalized in user["accountId"].casefold()
        ][:max_results]

    def search_users(self, query: str, max_results: int = 20) -> list[dict]:
        return self.find_assignable_users(self.project_key, query, max_results)

    def list_versions(self, project_key: str) -> list[dict]:
        return [_milestone_dict(item) for item in self.project.milestones.list(all=True, per_page=100)]

    def create_version(self, project_key: str, name: str, description: str = "", release_date: str | None = None) -> dict:
        data = {"title": name, "description": description}
        if release_date:
            data["due_date"] = release_date
        return _milestone_dict(self.project.milestones.create(data))

    def update_version(self, project_key: str, name: str, **fields) -> dict:
        milestone = self._get_milestone(name)
        for source, target in (("name", "title"), ("description", "description"), ("start_date", "start_date"), ("release_date", "due_date")):
            if source in fields:
                setattr(milestone, target, fields[source])
        if "released" in fields:
            milestone.state_event = "close" if fields["released"] else "activate"
        milestone.save()
        return _milestone_dict(milestone)

    def delete_version(self, project_key: str, name: str) -> bool:
        milestone = self._find_milestone(name)
        if milestone is None:
            return False
        milestone.delete()
        return True

    def list_labels(self, project_key: str) -> list[dict]:
        labels = self.project.labels.list(all=True, per_page=100)
        return [{"name": label.name, "color": str(getattr(label, "color", "") or "").lstrip("#"),
                 "description": getattr(label, "description", "") or "", "issueCount": ""} for label in labels]

    def create_label(self, project_key: str, name: str, color: str, description: str = "") -> dict:
        label = self.project.labels.create({"name": name, "color": _color(color), "description": description})
        return _label_dict(label)

    def update_label(self, project_key: str, name: str, new_name: str, color: str, description: str = "") -> dict:
        label = self.project.labels.get(name)
        label.name = new_name
        label.color = _color(color)
        label.description = description
        label.save()
        return _label_dict(label)

    def delete_label(self, project_key: str, name: str) -> None:
        self.project.labels.get(name).delete()

    def get_issue_comments(self, key: str, expand_changelog: bool = False) -> list[dict]:
        issue = self._get_issue(key)
        return [_note_dict(note) for note in issue.notes.list(all=True, per_page=100)]

    def find_children(self, key: str, max_results: int = 50) -> list:
        return []

    def add_comment(self, key: str, body: str | dict, use_adf: bool = False) -> dict:
        issue = self._get_issue(key)
        note = issue.notes.create({"body": body if isinstance(body, str) else str(body)})
        return {"id": str(note.id), "body": note.body}

    def update_issue(self, key: str, fields: dict) -> None:
        issue = self._get_issue(key)
        if "summary" in fields:
            issue.title = fields["summary"]
        if "description" in fields:
            issue.description = fields["description"]
        if "labels" in fields:
            issue.labels = fields["labels"]
        if "assignee" in fields:
            issue.assignee_ids = self._assignee_ids(fields["assignee"])
        issue.save()

    def create_issue(self, project_key: str, title: str, body=None, issue_type: str = "Task", labels=None,
                     assignee=None, priority=None, parent=None, repository=None) -> dict:
        data = {"title": title, "description": body if isinstance(body, str) else "", "labels": labels or []}
        if assignee:
            data["assignee_ids"] = self._assignee_ids(assignee)
        issue = self.project.issues.create(data)
        return {"key": self._key(issue.iid), "iid": issue.iid, "web_url": issue.web_url}

    def list_issue_repositories(self) -> list[str]:
        return []

    def get_transitions(self, key: str) -> list[dict]:
        issue = self._get_issue(key)
        next_state = "close" if issue.state == "opened" else "reopen"
        label = "Close" if next_state == "close" else "Reopen"
        return [{"id": next_state, "name": label, "to": {"name": "closed" if next_state == "close" else "opened"}}]

    def transition_issue(self, key: str, transition_id: str, comment: str | None = None) -> None:
        issue = self._get_issue(key)
        if transition_id not in {"close", "reopen"}:
            raise ValueError(f"Unsupported GitLab transition '{transition_id}'")
        issue.state_event = transition_id
        issue.save()
        if comment:
            issue.notes.create({"body": comment})

    def assign_issue(self, key: str, account_id: str) -> None:
        issue = self._get_issue(key)
        issue.assignee_ids = self._assignee_ids(account_id) if account_id else []
        issue.save()

    def list_timeline_items(self, project_key: str):
        from jira_cli.timeline import TimelineItem

        items = []
        for milestone in self.project.milestones.list(state="all", all=True, per_page=100):
            due = _as_date(getattr(milestone, "due_date", None))
            if due is None:
                continue
            start = _as_date(getattr(milestone, "start_date", None))
            if start is None:
                issues = self.project.issues.list(milestone=milestone.title, state="all", all=True, per_page=100)
                start = min((_as_date(issue.created_at) for issue in issues if _as_date(issue.created_at)), default=due)
            items.append(
                TimelineItem(
                    key=f"M{milestone.id}",
                    title=milestone.title,
                    start=start,
                    end=due,
                    status=getattr(milestone, "state", ""),
                    issue_type="Milestone",
                    target_url=str(getattr(milestone, "web_url", "") or ""),
                )
            )
        return items

    def list_timeline_markers(self, project_key: str) -> list:
        return []

    def _to_jira_issue(self, issue) -> JiraIssue:
        assignees = getattr(issue, "assignees", []) or []
        author = getattr(issue, "author", {}) or {}
        milestone = getattr(issue, "milestone", None) or {}
        return JiraIssue(
            key=self._key(issue.iid),
            fields=JiraIssueField(
                summary=issue.title,
                issuetype={"name": "Issue"},
                status={"name": issue.state},
                assignee={"accountId": str(assignees[0].get("id", "")), "displayName": assignees[0].get("name", "")}
                if assignees else None,
                reporter={"accountId": str(author.get("id", "")), "displayName": author.get("name", "")},
                updated=issue.updated_at,
                labels=list(issue.labels or []),
                description=issue.description or "",
                startDate=milestone.get("start_date") if isinstance(milestone, dict) else None,
                duedate=issue.due_date or (milestone.get("due_date") if isinstance(milestone, dict) else None),
            ),
        )

    def _key(self, iid: int | str) -> str:
        return f"{self.project_key}#{iid}"

    @staticmethod
    def _iid(key: str) -> int:
        match = re.search(r"#?(\d+)$", key)
        if not match:
            raise ValueError(f"Invalid GitLab issue key '{key}'")
        return int(match.group(1))

    def _get_issue(self, key: str):
        return self.project.issues.get(self._iid(key))

    def _find_milestone(self, name: str):
        return next((item for item in self.project.milestones.list(state="all", all=True) if item.title == name), None)

    def _get_milestone(self, name: str):
        milestone = self._find_milestone(name)
        if milestone is None:
            raise ValueError(f"GitLab milestone '{name}' not found")
        return self.project.milestones.get(milestone.id)

    def _assignee_ids(self, value: str) -> list[int]:
        if value.casefold() == "me":
            return [int(self.get_current_user()["accountId"])]
        user = next((user for user in self.list_assignable_users(self.project_key, 1000)
                     if value.casefold() in (user["accountId"].casefold(), user["displayName"].casefold())), None)
        return [int(user["accountId"])] if user else []


def _parse_jql(query: str) -> tuple[dict[str, str], str, str]:
    query_part, _, order_part = query.partition(" ORDER BY ")
    filters = {}
    for clause in query_part.split(" AND "):
        field, separator, raw = clause.partition("=")
        if not separator:
            continue
        field, value = field.strip().casefold(), raw.strip().strip('"')
        mapping = {"labels": "labels", "assignee": "assignee", "status": "status", "key": "key", "milestone": "milestone"}
        if field in mapping:
            filters[mapping[field]] = value
    if filters.get("key"):
        filters["key"] = filters["key"].rsplit("#", 1)[-1]
    if not order_part:
        return filters, "created_at", "desc"
    parts = order_part.split()
    field_map = {"created": "created_at", "updated": "updated_at", "key": "iid"}
    return filters, field_map.get(parts[0].casefold(), "created_at"), parts[1].casefold() if len(parts) > 1 else "asc"


def _matches(issue, filters: dict[str, str], project_key: str) -> bool:
    if filters.get("key") and str(issue.iid) != filters["key"]:
        return False
    if filters.get("status"):
        target = filters["status"].casefold()
        state = str(issue.state).casefold()
        if target in {"done", "closed", "resolved"}:
            if state != "closed":
                return False
        elif target not in {state, "open", "opened"}:
            return False
    return True


def _user_dict(user, include_private_email: bool = False) -> dict:
    email = getattr(user, "public_email", None)
    if include_private_email:
        email = getattr(user, "email", None) or email
    return {
        "accountId": str(getattr(user, "id", "")),
        "displayName": getattr(user, "name", "") or getattr(user, "username", ""),
        "emailAddress": email or "-",
        "active": getattr(user, "state", "active") == "active",
    }


def _milestone_dict(milestone) -> dict:
    return {
        "id": str(milestone.id),
        "name": milestone.title,
        "description": getattr(milestone, "description", "") or "",
        "startDate": getattr(milestone, "start_date", None),
        "releaseDate": getattr(milestone, "due_date", None),
        "released": getattr(milestone, "state", "active") == "closed",
        "archived": False,
    }


def _label_dict(label) -> dict:
    return {
        "name": label.name,
        "color": str(getattr(label, "color", "") or "").lstrip("#"),
        "description": getattr(label, "description", "") or "",
        "issueCount": "",
    }


def _note_dict(note) -> dict:
    author = getattr(note, "author", {}) or {}
    return {
        "author": {"displayName": author.get("name", "unknown")},
        "created": getattr(note, "created_at", ""),
        "body": getattr(note, "body", ""),
    }


def _color(value: str) -> str:
    cleaned = value.strip().lstrip("#")
    return f"#{cleaned}" if cleaned else "#428BCA"


def _as_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None
