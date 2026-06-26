"""Workflow feature services for Jira TUI."""

from dataclasses import dataclass
from typing import Any

from jira_cli.client import JiraClient
from jira_cli.models import IssueRow


@dataclass(frozen=True)
class TransitionActionContext:
    """UI context for transition action input."""

    issue_key: str
    input_mode: str
    mode_label: str
    choice_map: dict[str, str]
    notice: str
    placeholder: str


@dataclass(frozen=True)
class AssignActionContext:
    """UI context for assign action input."""

    issue_key: str
    input_mode: str
    mode_label: str
    placeholder: str


class JiraWorkflowFeature:
    """Encapsulate workflow operations and transition input parsing."""

    def __init__(self, client: JiraClient) -> None:
        self._client = client

    @staticmethod
    def parse_transition_expression(expression: str) -> tuple[str, str]:
        """Parse '<transition> | <comment>' input into its parts."""
        transition_input = expression.strip()
        comment = ""
        if "|" in expression:
            left, right = expression.split("|", 1)
            transition_input = left.strip()
            comment = right.strip()
        return transition_input, comment

    @staticmethod
    def build_transition_choice_map(transitions: list[dict[str, Any]]) -> tuple[dict[str, str], list[str]]:
        """Build lookup map and labels from Jira transition payload."""
        choice_map: dict[str, str] = {}
        labels: list[str] = []

        for transition in transitions:
            transition_id = str(transition.get("id", "")).strip()
            transition_name = str(transition.get("name", "")).strip()
            if not transition_id:
                continue

            choice_map[transition_id] = transition_id
            if transition_name:
                choice_map[transition_name.lower()] = transition_id
            labels.append(f"{transition_id}:{transition_name}")

        return choice_map, labels

    @staticmethod
    def resolve_transition_id(choice_map: dict[str, str], transition_input: str) -> str | None:
        """Resolve transition input against id/name map."""
        transition_id = choice_map.get(transition_input)
        if transition_id:
            return transition_id
        return choice_map.get(transition_input.lower())

    def apply_transition(self, issue_key: str, transition_id: str, comment: str = "") -> None:
        """Apply transition to issue."""
        self._client.transition_issue(issue_key, transition_id, comment=comment or None)

    def assign_issue(self, issue_key: str, assignee: str) -> None:
        """Assign issue to account/email."""
        self._client.assign_issue(issue_key, assignee)

    def prepare_transition_action(self, issue: IssueRow | None) -> TransitionActionContext:
        """Build transition action context for selected issue."""
        if not issue:
            raise ValueError("No issue selected")

        transitions = self._client.get_transitions(issue.key)
        if not transitions:
            raise ValueError(f"No transitions available for {issue.key}")

        choice_map, labels = self.build_transition_choice_map(transitions)
        return TransitionActionContext(
            issue_key=issue.key,
            input_mode="transition",
            mode_label="MODE: TRANSITION (INPUT)",
            choice_map=choice_map,
            notice="Transitions: " + " | ".join(labels),
            placeholder="Transition ID or name; optional comment with: <transition> | <comment>",
        )

    def submit_transition_expression(self, issue_key: str, expression: str, choice_map: dict[str, str]) -> str:
        """Validate and apply transition expression."""
        transition_input, comment = self.parse_transition_expression(expression)
        transition_id = self.resolve_transition_id(choice_map, transition_input)
        if not transition_id:
            raise ValueError("Unknown transition. Use shown ID or exact name.")
        self.apply_transition(issue_key, transition_id, comment=comment)
        return f"Transitioned {issue_key}"

    def prepare_assign_action(self, issue: IssueRow | None) -> AssignActionContext:
        """Build assign action context for selected issue."""
        if not issue:
            raise ValueError("No issue selected")
        return AssignActionContext(
            issue_key=issue.key,
            input_mode="assign",
            mode_label="MODE: ASSIGN (INPUT)",
            placeholder="Assignee (email/account) and press Enter",
        )

    def submit_assign_expression(self, issue_key: str, expression: str) -> str:
        """Apply assign expression."""
        self.assign_issue(issue_key, expression)
        return f"Assigned {issue_key} to {expression}"
