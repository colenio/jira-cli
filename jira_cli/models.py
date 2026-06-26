"""Pydantic models for Jira API responses."""

from typing import Optional

from pydantic import BaseModel, Field


class JiraUser(BaseModel):
    """Jira user representation."""

    key: str
    display_name: str = Field(alias="displayName")
    email: Optional[str] = None
    avatar_url: Optional[str] = Field(None, alias="avatarUrls")

    class Config:
        populate_by_name = True


class JiraIssueField(BaseModel):
    """Jira issue field (stripped down)."""

    summary: str
    status: Optional[dict | str] = None
    priority: Optional[dict | str] = None
    assignee: Optional[dict] = None
    reporter: Optional[dict] = None
    issuetype: Optional[dict | str] = None
    parent: Optional[dict] = None
    subtasks: list[dict] = []
    labels: list[str] = []
    created: Optional[str] = None
    updated: Optional[str] = None
    description: Optional[str] = None

    class Config:
        extra = "allow"


class JiraIssue(BaseModel):
    """Complete Jira issue."""

    key: str
    fields: JiraIssueField

    class Config:
        extra = "allow"


class JiraSearchResult(BaseModel):
    """Response from Jira search endpoint."""

    issues: list[JiraIssue] = []
    total: int = 0
    max_results: int = Field(0, alias="maxResults")
    start_at: int = Field(0, alias="startAt")
    next_page_token: Optional[str] = Field(None, alias="nextPageToken")

    class Config:
        populate_by_name = True


class IssueRow(BaseModel):
    """Flattened issue for table/csv output."""

    key: str
    summary: str
    issue_type: str = ""
    issue_type_emoji: str = ""
    status: str = ""
    priority: str = ""
    assignee: str = ""
    updated: str = ""
    labels: str = ""
    parent_key: str = ""
    child_keys: list[str] = Field(default_factory=list)

    @staticmethod
    def issue_type_to_emoji(issue_type: str) -> str:
        """Map common Jira issue types to emoji."""
        normalized = (issue_type or "").strip().lower()
        mapping = {
            "epic": "🚀",
            "story": "📘",
            "bug": "🐞",
            "task": "✅",
            "sub-task": "🧩",
            "subtask": "🧩",
            "incident": "🔥",
        }
        return mapping.get(normalized, "📄")

    @staticmethod
    def from_jira_issue(issue: JiraIssue) -> "IssueRow":
        """Convert Jira issue to flattened row."""
        fields = issue.fields

        status = ""
        if isinstance(fields.status, dict):
            status = fields.status.get("name", "")
        elif isinstance(fields.status, str):
            status = fields.status

        priority = ""
        if isinstance(fields.priority, dict):
            priority = fields.priority.get("name", "")
        elif isinstance(fields.priority, str):
            priority = fields.priority

        assignee = ""
        if fields.assignee:
            assignee = (
                fields.assignee.get("displayName")
                or fields.assignee.get("name")
                or fields.assignee.get("accountId")
                or fields.assignee.get("key", "")
            )
        
        labels = ", ".join(fields.labels) if fields.labels else ""
        issue_type = ""
        if isinstance(fields.issuetype, dict):
            issue_type = fields.issuetype.get("name", "")
        elif isinstance(fields.issuetype, str):
            issue_type = fields.issuetype

        parent_key = ""
        if fields.parent:
            parent_key = fields.parent.get("key", "")

        child_keys: list[str] = []
        if fields.subtasks:
            child_keys = [subtask.get("key", "") for subtask in fields.subtasks if subtask.get("key")]
        
        return IssueRow(
            key=issue.key,
            summary=fields.summary,
            issue_type=issue_type,
            issue_type_emoji=IssueRow.issue_type_to_emoji(issue_type),
            status=status,
            priority=priority,
            assignee=assignee,
            updated=fields.updated or "",
            labels=labels,
            parent_key=parent_key,
            child_keys=child_keys,
        )
