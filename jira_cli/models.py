"""Pydantic models for Jira API responses."""

from datetime import datetime
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
    status: str = ""
    priority: str = ""
    assignee: str = ""
    updated: str = ""
    labels: str = ""

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
        
        return IssueRow(
            key=issue.key,
            summary=fields.summary,
            status=status,
            priority=priority,
            assignee=assignee,
            updated=fields.updated or "",
            labels=labels,
        )
