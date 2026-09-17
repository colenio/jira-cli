"""Synthetic Jira data source for screenshots, demos, and docs."""

from __future__ import annotations

from typing import Optional

from jira_cli.models import JiraIssue, JiraIssueField, JiraSearchResult
from jira_cli.quick_filters import normalize_for_match

DEMO_PROJECT_KEY = "DEMO"

_DEMO_ISSUES = [
    {
        "key": "DEMO-10",
        "summary": "CLI foundation",
        "issuetype": "Epic",
        "status": "In Progress",
        "priority": "High",
        "assignee": "Marcel Körtgen",
        "updated": "2026-09-12T09:00:00.000+0000",
        "startDate": "2026-08-01",
        "dueDate": "2026-10-31",
        "labels": ["roadmap", "cli"],
        "description": "Core provider-neutral CLI and TUI foundation.",
        "reporter": "Ada Lovelace",
    },
    {
        "key": "DEMO-11",
        "summary": "Provider expansion",
        "issuetype": "Epic",
        "status": "To Do",
        "priority": "Medium",
        "assignee": "Grace Hopper",
        "updated": "2026-09-12T10:00:00.000+0000",
        "startDate": "2026-10-15",
        "dueDate": "2027-01-31",
        "labels": ["roadmap", "providers"],
        "description": "GitHub, Jira, and future provider capabilities.",
        "reporter": "Marcel Körtgen",
    },
    {
        "key": "DEMO-12",
        "summary": "Documentation and release",
        "issuetype": "Epic",
        "status": "Backlog",
        "priority": "Low",
        "assignee": "Katherine Johnson",
        "updated": "2026-09-12T11:00:00.000+0000",
        "startDate": "2027-01-01",
        "dueDate": "2027-03-31",
        "labels": ["roadmap", "docs"],
        "description": "Documentation site, examples, and the next release.",
        "reporter": "Ada Lovelace",
    },
    {
        "key": "DEMO-1",
        "summary": "Roll out dependency update workflow",
        "issuetype": "Story",
        "status": "Backlog",
        "priority": "High",
        "assignee": "Ada Lovelace",
        "updated": "2026-09-10T09:30:00.000+0000",
        "labels": ["automation", "security"],
        "description": "Coordinate the dependency update rollout. See [the release checklist](https://example.invalid/checklist).",
        "reporter": "Marcel Körtgen",
        "subtasks": ["DEMO-6", "DEMO-7"],
    },
    {
        "key": "DEMO-2",
        "summary": "Review API token handling in CLI docs",
        "issuetype": "Task",
        "status": "To Do",
        "priority": "Medium",
        "assignee": "Grace Hopper",
        "updated": "2026-09-10T11:15:00.000+0000",
        "labels": ["docs"],
        "description": "Document token handling and the supported environment variables.",
        "reporter": "Ada Lovelace",
    },
    {
        "key": "DEMO-3",
        "summary": "Fix flaky TUI selection after refresh",
        "issuetype": "Bug",
        "status": "In Progress",
        "priority": "Highest",
        "assignee": "Marcel Körtgen",
        "updated": "2026-09-11T08:05:00.000+0000",
        "labels": ["tui", "quality"],
        "description": "Selection must survive refresh and keep the detail pane in sync.",
        "reporter": "Grace Hopper",
    },
    {
        "key": "DEMO-4",
        "summary": "Prepare release notes for v0.5.0",
        "issuetype": "Task",
        "status": "In Review",
        "priority": "Low",
        "assignee": "Katherine Johnson",
        "updated": "2026-09-11T13:40:00.000+0000",
        "labels": ["release"],
        "description": "Collect the user-facing changes for the next demo release.",
        "reporter": "Marcel Körtgen",
    },
    {
        "key": "DEMO-5",
        "summary": "Publish MkDocs API reference",
        "issuetype": "Story",
        "status": "Done",
        "priority": "Medium",
        "assignee": "Grace Hopper",
        "updated": "2026-09-11T16:20:00.000+0000",
        "labels": ["docs", "automation"],
        "description": "Publish the generated API reference after the build succeeds.",
        "reporter": "Katherine Johnson",
    },
    {
        "key": "DEMO-6",
        "summary": "Add dependency update acceptance checks",
        "issuetype": "Sub-task",
        "status": "To Do",
        "priority": "Medium",
        "assignee": "Ada Lovelace",
        "updated": "2026-09-10T10:00:00.000+0000",
        "labels": ["automation"],
        "parent": "DEMO-1",
        "reporter": "Marcel Körtgen",
    },
    {
        "key": "DEMO-7",
        "summary": "Add dependency update rollback notes",
        "issuetype": "Sub-task",
        "status": "Backlog",
        "priority": "Low",
        "assignee": "Grace Hopper",
        "updated": "2026-09-10T10:30:00.000+0000",
        "labels": ["security"],
        "parent": "DEMO-1",
        "reporter": "Marcel Körtgen",
    },
]

_DEMO_USERS = [
    {"accountId": "demo-ada", "displayName": "Ada Lovelace", "emailAddress": "ada@example.invalid", "active": True},
    {"accountId": "demo-grace", "displayName": "Grace Hopper", "emailAddress": "grace@example.invalid", "active": True},
    {"accountId": "demo-marcel", "displayName": "Marcel Körtgen", "emailAddress": "marcel@example.invalid", "active": True},
    {"accountId": "demo-katherine", "displayName": "Katherine Johnson", "emailAddress": "katherine@example.invalid", "active": True},
]

_DEMO_VERSIONS = [
    {"id": "demo-v050", "name": "v0.5.0", "description": "TUI resource views", "releaseDate": "2026-09-12", "released": False, "archived": False},
    {"id": "demo-v040", "name": "v0.4.0", "description": "CLI command groups", "releaseDate": "2026-08-30", "released": True, "archived": False},
]

_DEMO_COMMENTS = {
    "DEMO-3": [
        {
            "author": {"displayName": "Grace Hopper"},
            "created": "2026-09-11T08:20:00.000+0000",
            "body": "Reproduced in demo mode; prefetch should keep navigation responsive.",
        }
    ]
}


class DemoJiraClient:
    """JiraClient-compatible synthetic data source for safe screenshots."""

    base_url = "https://demo.atlassian.invalid"
    dry_run = True

    def search(
        self,
        jql: str,
        fields: Optional[list[str]] = None,
        start_at: int = 0,
        max_results: int = 50,
        expand: Optional[list[str]] = None,
    ) -> JiraSearchResult:
        """Search demo issues using the small JQL subset generated by JiraQuery."""
        rows = _filter_issues(jql)
        page = rows[start_at : start_at + max_results]
        return JiraSearchResult(issues=[_to_jira_issue(issue) for issue in page], total=len(rows), startAt=start_at, maxResults=max_results)

    def get_current_user(self) -> dict:
        """Return the synthetic authenticated user."""
        return _DEMO_USERS[2]

    def list_assignable_users(self, project_key: str, max_results: int = 50) -> list[dict]:
        """Return synthetic assignable users."""
        return _DEMO_USERS[:max_results]

    def find_assignable_users(self, project_key: str, query: str, max_results: int = 20) -> list[dict]:
        """Search synthetic assignable users."""
        normalized_query = normalize_for_match(query)
        users = [user for user in _DEMO_USERS if normalized_query in normalize_for_match(user.get("displayName", ""))]
        return users[:max_results]

    def search_users(self, query: str, max_results: int = 20) -> list[dict]:
        """Search synthetic users globally."""
        return self.find_assignable_users(DEMO_PROJECT_KEY, query, max_results=max_results)

    def list_versions(self, project_key: str) -> list[dict]:
        """Return synthetic fix versions/milestones."""
        return list(_DEMO_VERSIONS)

    def list_labels(self, project_key: str) -> list[dict]:
        """Return synthetic labels with issue counts."""
        counts: dict[str, int] = {}
        for issue in _DEMO_ISSUES:
            for label in issue["labels"]:
                counts[label] = counts.get(label, 0) + 1
        return [{"name": name, "issueCount": count} for name, count in sorted(counts.items())]

    def create_version(self, project_key: str, name: str, description: str = "", release_date: str | None = None) -> dict:
        version = {
            "id": f"demo-{normalize_for_match(name).replace(' ', '-')}",
            "name": name,
            "description": description,
            "releaseDate": release_date,
            "released": False,
            "archived": False,
        }
        _DEMO_VERSIONS.append(version)
        return version

    def update_version(self, project_key: str, name: str, **fields) -> dict:
        version = next(version for version in _DEMO_VERSIONS if version["name"] == name)
        version.update(fields)
        return version

    def delete_version(self, project_key: str, name: str) -> bool:
        before = len(_DEMO_VERSIONS)
        _DEMO_VERSIONS[:] = [version for version in _DEMO_VERSIONS if version["name"] != name]
        return len(_DEMO_VERSIONS) < before

    def create_label(self, project_key: str, name: str, color: str, description: str = "") -> dict:
        return {"name": name, "color": color, "description": description, "issueCount": 0}

    def update_label(self, project_key: str, name: str, new_name: str, color: str, description: str = "") -> dict:
        return {"name": new_name, "color": color, "description": description, "issueCount": 0}

    def delete_label(self, project_key: str, name: str) -> None:
        return None

    def get_issue_comments(self, key: str, expand_changelog: bool = False) -> list[dict]:
        """Return synthetic comments for one issue."""
        return list(_DEMO_COMMENTS.get(key, []))

    def find_children(self, key: str, max_results: int = 50) -> list[IssueRow]:
        """Return synthetic issues whose parent matches the requested key."""
        return [
            IssueRow.from_jira_issue(_to_jira_issue(issue))
            for issue in _DEMO_ISSUES
            if issue.get("parent") == key
        ][:max_results]

    def add_comment(self, key: str, body: str | dict, use_adf: bool = False) -> dict:
        """Pretend to add a comment in demo mode."""
        return {"id": "demo-comment", "body": body}

    def create_issue(
        self,
        project_key: str,
        title: str,
        body: str | dict | None = None,
        issue_type: str = "Task",
        labels: list[str] | None = None,
        assignee: str | None = None,
        priority: str | None = None,
        parent: str | None = None,
        repository: str | None = None,
    ) -> dict:
        """Create an in-memory synthetic issue for demo interactions."""
        number = max(int(issue["key"].split("-")[-1]) for issue in _DEMO_ISSUES) + 1
        issue = {
            "key": f"{DEMO_PROJECT_KEY}-{number}",
            "summary": title,
            "issuetype": issue_type,
            "status": "To Do",
            "priority": priority or "Medium",
            "assignee": assignee or "",
            "updated": "2026-09-16T09:00:00.000+0000",
            "labels": labels or [],
            "description": body if isinstance(body, str) else "",
            "parent": parent,
            "reporter": "Marcel Körtgen",
        }
        _DEMO_ISSUES.append(issue)
        return {"key": issue["key"], "id": issue["key"]}

    def update_issue(self, key: str, fields: dict) -> None:
        """Pretend to update an issue in demo mode."""
        issue = next((issue for issue in _DEMO_ISSUES if issue["key"] == key), None)
        if issue:
            issue.update(
                {
                    "summary": fields.get("summary", issue["summary"]),
                    "description": fields.get("description", issue.get("description", "")),
                    "labels": fields.get("labels", issue["labels"]),
                    "priority": fields.get("priority", issue["priority"]),
                }
            )

    def get_transitions(self, key: str) -> list[dict]:
        """Return synthetic workflow transitions."""
        return [{"id": "demo-done", "name": "Done"}, {"id": "demo-progress", "name": "In Progress"}]

    def transition_issue(self, key: str, transition_id: str, comment: str | None = None) -> None:
        """Pretend to transition an issue in demo mode."""
        status = {"demo-done": "Done", "demo-progress": "In Progress"}.get(transition_id)
        issue = next((issue for issue in _DEMO_ISSUES if issue["key"] == key), None)
        if issue and status:
            issue["status"] = status

    def assign_issue(self, key: str, account_id: str) -> None:
        """Pretend to assign an issue in demo mode."""
        user = next((user for user in _DEMO_USERS if user["accountId"] == account_id), None)
        issue = next((issue for issue in _DEMO_ISSUES if issue["key"] == key), None)
        if issue and user:
            issue["assignee"] = user["displayName"]


def _to_jira_issue(issue: dict) -> JiraIssue:
    assignee = next((user for user in _DEMO_USERS if user["displayName"] == issue["assignee"]), None)
    return JiraIssue(
        key=issue["key"],
        fields=JiraIssueField(
            summary=issue["summary"],
            issuetype={"name": issue["issuetype"]},
            status={"name": issue["status"]},
            priority={"name": issue["priority"]},
            assignee=assignee,
            updated=issue["updated"],
            labels=issue["labels"],
            description=issue.get("description"),
            customfield_10015=issue.get("startDate"),
            duedate=issue.get("dueDate"),
            reporter=(
                {"displayName": issue["reporter"]}
                if issue.get("reporter")
                else None
            ),
            parent={"key": issue["parent"]} if issue.get("parent") else None,
            subtasks=[{"key": key} for key in issue.get("subtasks", [])],
        ),
    )


def _filter_issues(jql: str) -> list[dict]:
    query_part, _, order_part = jql.partition(" ORDER BY ")
    conditions = [condition.strip() for condition in query_part.split(" AND ")]
    rows = [issue for issue in _DEMO_ISSUES if _matches(issue, conditions)]
    return _sort_issues(rows, order_part)


def _matches(issue: dict, conditions: list[str]) -> bool:
    for condition in conditions:
        if not condition or condition.startswith("project ="):
            continue
        if condition == "assignee = currentUser()":
            if issue["assignee"] != "Marcel Körtgen":
                return False
            continue
        field, _, raw_value = condition.partition("=")
        field = field.strip()
        value = raw_value.strip().strip('"')
        if field == "key" and issue["key"] != value:
            return False
        if field == "issuetype" and issue["issuetype"] != value:
            return False
        if field == "status" and issue["status"] != value:
            return False
        if field == "assignee" and issue["assignee"] != value:
            return False
        if field == "priority" and issue["priority"] != value:
            return False
        if field == "labels" and value not in issue["labels"]:
            return False
        if field == "parent" and issue.get("parent") != value:
            return False
    return True


def _sort_issues(rows: list[dict], order_part: str) -> list[dict]:
    if not order_part:
        return rows
    parts = order_part.split()
    field = parts[0]
    reverse = len(parts) > 1 and parts[1].upper() == "DESC"
    accessors = {
        "key": lambda issue: issue["key"],
        "priority": lambda issue: issue["priority"],
        "status": lambda issue: issue["status"],
        "issuetype": lambda issue: issue["issuetype"],
        "updated": lambda issue: issue["updated"],
    }
    accessor = accessors.get(field)
    return sorted(rows, key=accessor, reverse=reverse) if accessor else rows
