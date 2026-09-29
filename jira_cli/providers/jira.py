"""Jira provider implementation."""

from __future__ import annotations

import os

from jira_cli.client import JiraClient
from jira.exceptions import JIRAError

from .base import ActionDescriptor, FilterDescriptor, ProviderDescriptor, ResourceDescriptor, SortDescriptor

JIRA_PROVIDER_DESCRIPTOR = ProviderDescriptor(
    name="jira",
    query_language="JQL",
    token_env="JIRA_API_TOKEN",
    token_url="https://id.atlassian.com/manage-profile/security/api-tokens",
    resources=(
        ResourceDescriptor(
            kind="issues",
            fields=("key", "summary", "type", "status", "assignee", "reporter", "priority", "labels", "updated", "parent"),
            filters=(
                FilterDescriptor(name="type", field="issuetype"),
                FilterDescriptor(name="status", field="status"),
                FilterDescriptor(name="assignee", field="assignee", special_values=("me", "none")),
                FilterDescriptor(name="label", field="labels"),
                FilterDescriptor(name="priority", field="priority"),
                FilterDescriptor(name="key", field="key"),
            ),
            sorts=(
                SortDescriptor(name="key", field="key"),
                SortDescriptor(name="priority", field="priority"),
                SortDescriptor(name="updated", field="updated", default_direction="desc"),
                SortDescriptor(name="status", field="status"),
                SortDescriptor(name="rank", field="Rank"),
            ),
            actions=(
                ActionDescriptor(name="create"),
                ActionDescriptor(name="comment"),
                ActionDescriptor(name="assign"),
                ActionDescriptor(name="transition"),
                ActionDescriptor(name="close"),
                ActionDescriptor(name="reopen"),
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
            actions=(
                ActionDescriptor(name="create"),
                ActionDescriptor(name="edit"),
                ActionDescriptor(name="delete"),
                ActionDescriptor(name="release"),
            ),
        ),
        ResourceDescriptor(
            kind="labels",
            fields=("name", "issueCount"),
            actions=(ActionDescriptor(name="edit"), ActionDescriptor(name="delete")),
        ),
        ResourceDescriptor(
            kind="components",
            fields=("name", "description", "lead", "assigneeType"),
        ),
        ResourceDescriptor(
            kind="sprints",
            fields=("name", "state", "startDate", "endDate", "completeDate", "board", "goal"),
        ),
    ),
)


class JiraProvider(JiraClient):
    """Jira-backed issue tracker provider."""

    _start_date_field: str | None = None
    _sprint_field_id: str | None = None

    def describe(self) -> ProviderDescriptor:
        """Describe Jira-native resources and capabilities."""
        return JIRA_PROVIDER_DESCRIPTOR

    def find_children(self, key: str, max_results: int = 50) -> list:
        """Find Epic or sub-task children through Jira's parent field."""
        from jira_cli.models import IssueRow

        result = self.search(f"parent = {key} ORDER BY key", max_results=max_results)
        return [IssueRow.from_jira_issue(issue, self.start_date_field()) for issue in result.issues]

    def sprint_field(self) -> str:
        """Resolve Jira's Sprint custom field from field metadata once."""
        if self._sprint_field_id is not None:
            return self._sprint_field_id
        try:
            fields = self._jira.fields()
        except Exception:
            fields = []
        sprint_fields = [
            field
            for field in fields
            if str(field.get("name", "")).strip().casefold() == "sprint"
        ]
        sprint_fields.sort(
            key=lambda field: "gh-sprint" not in str(field.get("schema", {}).get("custom", "")).casefold()
        )
        self._sprint_field_id = str(sprint_fields[0].get("id", "")) if sprint_fields else ""
        return self._sprint_field_id

    def list_epic_sprint_assignments(self, project_key: str) -> dict[str, list[str]]:
        """Map each Epic to Sprint IDs found on its child issues."""
        sprint_field = self.sprint_field()
        if not sprint_field:
            return {}

        assignments: dict[str, set[str]] = {}
        start_at = 0
        while True:
            result = self.search(
                f"project = {project_key} AND parent IS NOT EMPTY ORDER BY key",
                fields=["summary", "parent", sprint_field],
                start_at=start_at,
                max_results=100,
            )
            for issue in result.issues:
                parent = issue.fields.parent
                parent_key = parent.get("key", "") if isinstance(parent, dict) else ""
                if not parent_key:
                    continue
                raw_sprints = (issue.fields.model_extra or {}).get(sprint_field) or []
                if isinstance(raw_sprints, dict):
                    raw_sprints = [raw_sprints]
                for sprint in raw_sprints:
                    sprint_id = sprint.get("id") if isinstance(sprint, dict) else None
                    if sprint_id is not None:
                        assignments.setdefault(parent_key, set()).add(str(sprint_id))
            start_at += len(result.issues)
            if not result.issues or start_at >= result.total:
                break
        return {key: sorted(sprint_ids) for key, sprint_ids in assignments.items()}

    def list_timeline_items(self, project_key: str):
        """Return Jira Epics as planning items, enriched with their children's Sprint assignments."""
        from datetime import date

        from jira_cli.models import IssueRow
        from jira_cli.timeline import TimelineItem

        sprint_assignments = self.list_epic_sprint_assignments(project_key)
        start_field = self.start_date_field()
        fields = ["summary", "issuetype", "status", "parent", "duedate"]
        if start_field:
            fields.append(start_field)
        start_at = 0
        items = []
        while True:
            result = self.search(
                f"project = {project_key} AND issuetype = Epic ORDER BY key",
                fields=fields,
                start_at=start_at,
                max_results=100,
            )
            for issue in result.issues:
                row = IssueRow.from_jira_issue(issue, start_field)
                try:
                    start = date.fromisoformat(row.start_date[:10]) if row.start_date else None
                except ValueError:
                    start = None
                try:
                    end = date.fromisoformat(row.due_date[:10]) if row.due_date else None
                except ValueError:
                    end = None
                items.append(
                    TimelineItem(
                        row.key,
                        row.summary,
                        start,
                        end,
                        row.status,
                        row.parent_key,
                        row.issue_type or "Epic",
                        tuple(sprint_assignments.get(row.key, [])),
                        self.get_issue_url(row.key),
                    )
                )
            start_at += len(result.issues)
            if not result.issues or start_at >= result.total:
                break
        return items

    def start_date_field(self) -> str:
        """Resolve a Jira start-date field once, allowing an explicit environment override."""
        if self._start_date_field is not None:
            return self._start_date_field
        configured = os.environ.get("JIRA_START_DATE_FIELD", "").strip()
        if configured:
            self._start_date_field = configured
            return configured
        try:
            candidates = [
                field["id"]
                for field in self._jira.fields()
                if field.get("schema", {}).get("type") == "date"
                and field.get("name", "").strip().casefold() == "start date"
            ]
        except Exception:
            candidates = []
        self._start_date_field = "customfield_10015" if "customfield_10015" in candidates else (candidates[0] if candidates else "")
        return self._start_date_field

    def list_resource(self, kind: str, project_key: str) -> list[dict]:
        """List Jira Components or Sprints for the active project."""
        if kind == "components":
            components = []
            for component in self._jira.project_components(project_key):
                raw = component.raw
                lead = raw.get("lead") or {}
                components.append(
                    {
                        "id": str(raw.get("id", "")),
                        "name": raw.get("name", ""),
                        "description": raw.get("description", "") or "",
                        "lead": lead.get("displayName") or raw.get("leadUserName") or "",
                        "assigneeType": raw.get("assigneeType", "") or "",
                    }
                )
            return components
        if kind == "sprints":
            sprints: dict[str, dict] = {}
            board_start = 0
            while True:
                boards = self._jira.boards(projectKeyOrID=project_key, startAt=board_start, maxResults=50)
                for board in boards:
                    sprint_start = 0
                    while True:
                        try:
                            page = self._jira.sprints(
                                board.id,
                                state="active,future,closed",
                                startAt=sprint_start,
                                maxResults=50,
                            )
                        except JIRAError as error:
                            if "does not support sprints" in (error.text or "").casefold():
                                break
                            raise
                        for sprint in page:
                            sprint_data = dict(sprint.raw)
                            sprint_data["board"] = board.name
                            sprints[str(sprint.id)] = sprint_data
                        sprint_start += len(page)
                        if not page or sprint_start >= getattr(page, "total", len(page)):
                            break
                board_start += len(boards)
                if not boards or board_start >= getattr(boards, "total", len(boards)):
                    break
            state_order = {"active": 0, "future": 1, "closed": 2}
            return sorted(
                sprints.values(),
                key=lambda sprint: (
                    state_order.get(str(sprint.get("state", "")).casefold(), 3),
                    sprint.get("startDate") or "",
                    sprint.get("name", ""),
                ),
            )
        raise ValueError(f"Unsupported Jira resource '{kind}'")

    def update_label(
        self, project_key: str, name: str, new_name: str, color: str, description: str = ""
    ) -> dict:
        """Rename a Jira label on every matching issue in the project."""
        issues = self._jira.enhanced_search_issues(
            jql_str=f'project = {project_key} AND labels = "{name}"',
            maxResults=False,
            fields=["labels"],
        )
        for issue in issues:
            labels = [new_name if label == name else label for label in (issue.fields.labels or [])]
            issue.update(fields={"labels": list(dict.fromkeys(labels))})
        return {"name": new_name, "issueCount": len(issues)}

    def delete_label(self, project_key: str, name: str) -> None:
        """Remove a Jira label from every matching issue in the project."""
        issues = self._jira.enhanced_search_issues(
            jql_str=f'project = {project_key} AND labels = "{name}"',
            maxResults=False,
            fields=["labels"],
        )
        for issue in issues:
            issue.update(fields={"labels": [label for label in (issue.fields.labels or []) if label != name]})
