"""Tests for Jira CLI."""

import pytest

from jira_cli.models import IssueRow, JiraIssue, JiraIssueField
from jira_cli.dotenv import DotEnv


def test_issue_row_from_jira_issue():
    """Test converting Jira issue to flattened row."""
    issue = JiraIssue(
        key="TEST-123",
        fields=JiraIssueField(
            key="TEST-123",
            summary="Fix database query",
            status="In Progress",
            priority="High",
            assignee={"displayName": "John Doe", "key": "john"},
            labels=["bug", "urgent"],
            description="Detailed issue description",
            updated="2026-06-23T10:30:00.000+0000",
        ),
    )

    row = IssueRow.from_jira_issue(issue)

    assert row.key == "TEST-123"
    assert row.summary == "Fix database query"
    assert row.status == "In Progress"
    assert row.priority == "High"
    assert row.assignee == "John Doe"
    assert row.labels == "bug, urgent"
    assert row.description == "Detailed issue description"


def test_jira_adf_description_is_normalized_to_text():
    issue = JiraIssue(
        key="TEST-ADF",
        fields=JiraIssueField(
            summary="ADF issue",
            description={
                "type": "doc",
                "version": 1,
                "content": [
                    {"type": "paragraph", "content": [{"type": "text", "text": "First paragraph"}]},
                    {"type": "paragraph", "content": [{"type": "text", "text": "Second paragraph"}]},
                ],
            },
        ),
    )

    assert issue.fields.description == "First paragraph\n\nSecond paragraph"


def test_issue_row_reads_jira_custom_start_date():
    issue = JiraIssue(
        key="TEST-DATE",
        fields=JiraIssueField(
            summary="Planned work",
            customfield_10015="2026-09-01",
            duedate="2026-09-30",
        ),
    )

    row = IssueRow.from_jira_issue(issue)

    assert row.start_date == "2026-09-01"
    assert row.due_date == "2026-09-30"


def test_dotenv_basic(tmp_path):
    """Test DotEnv loading."""
    # Create a test .env file
    env_file = tmp_path / ".env"
    env_file.write_text("TEST_VAR=test_value\nANOTHER=123\n")

    # Would need to mock os.getcwd() to test properly
    # This is a placeholder for actual implementation
    assert env_file.exists()


if __name__ == "__main__":
    pytest.main([__file__])
