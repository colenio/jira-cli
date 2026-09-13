"""Tests for provider-driven transition UX and mandatory comments."""

import pytest

from jira_cli.models import IssueRow
from jira_cli.tui.features.workflow.service import JiraWorkflowFeature


class FakeWorkflowProvider:
    def __init__(self):
        self.calls = []

    def get_transitions(self, key: str) -> list[dict]:
        return [
            {"id": "11", "name": "Start", "to": {"name": "In Progress"}},
            {"id": "21", "name": "Finish", "to": {"name": "Done"}},
        ]

    def transition_issue(self, key: str, transition_id: str, comment: str | None = None) -> None:
        self.calls.append((key, transition_id, comment))


def test_next_transition_selects_next_board_status() -> None:
    provider = FakeWorkflowProvider()
    feature = JiraWorkflowFeature(provider)

    context = feature.prepare_next_transition_action(
        IssueRow(key="DEMO-1", summary="Issue", status="In Progress"),
        ["Backlog", "To Do", "In Progress", "Done"],
    )

    assert context.default_transition_id == "21"
    assert context.notice == "Next: In Progress -> Done"


def test_transition_requires_comment() -> None:
    provider = FakeWorkflowProvider()
    feature = JiraWorkflowFeature(provider)

    with pytest.raises(ValueError, match="comment is required"):
        feature.submit_transition_expression("DEMO-1", "21", {"21": "21"})


def test_next_transition_applies_comment_to_selected_transition() -> None:
    provider = FakeWorkflowProvider()
    feature = JiraWorkflowFeature(provider)

    result = feature.submit_transition_expression(
        "DEMO-1", "Finished the work", {"21": "21"}, default_transition_id="21"
    )

    assert result == "Transitioned DEMO-1"
    assert provider.calls == [("DEMO-1", "21", "Finished the work")]
