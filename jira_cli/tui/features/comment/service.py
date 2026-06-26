"""Comment feature services for Jira TUI."""

from dataclasses import dataclass
import json
from typing import Any

from jira_cli.client import JiraClient
from jira_cli.models import IssueRow

from .validation import validate_adf_doc, validate_markdown_text


@dataclass(frozen=True)
class CommentActionContext:
    """UI context for entering comment mode."""

    issue_key: str
    input_mode: str
    mode_label: str
    placeholder: str


class JiraCommentFeature:
    """Encapsulate comment parsing, cache loading, and navigation state."""

    def __init__(self, client: JiraClient) -> None:
        self._client = client
        self._issue_comments: dict[str, list[dict[str, Any]]] = {}
        self._issue_comment_index: dict[str, int] = {}

    def normalize_input(self, expression: str) -> tuple[str, str]:
        """Parse comment input mode prefix and payload."""
        mode = "plain"
        payload = expression
        if expression.startswith("md:"):
            mode = "md"
            payload = expression[3:].strip()
        elif expression.startswith("adf:"):
            mode = "adf"
            payload = expression[4:].strip()
        elif expression.startswith("plain:"):
            payload = expression[6:].strip()
        return mode, payload

    def prepare_comment_action(self, issue: IssueRow | None) -> CommentActionContext:
        """Create input context for comment action."""
        if not issue:
            raise ValueError("No issue selected")
        return CommentActionContext(
            issue_key=issue.key,
            input_mode="comment",
            mode_label="MODE: COMMENT (INPUT)",
            placeholder="Comment: plain:<text> | md:<markdown> | adf:<json> (default is plain)",
        )

    def submit_comment_expression(self, issue_key: str, expression: str) -> str:
        """Validate and submit comment expression, returning success message."""
        mode, payload = self.normalize_input(expression)

        if mode == "adf":
            try:
                adf_doc = json.loads(payload)
            except json.JSONDecodeError as decode_error:
                raise ValueError(f"Invalid ADF JSON: {decode_error}") from decode_error

            valid, error = validate_adf_doc(adf_doc)
            if not valid:
                raise ValueError(f"Invalid ADF: {error}")

            self._client.add_comment(issue_key, adf_doc, use_adf=True)
            return f"Added ADF comment to {issue_key}"

        if mode == "md":
            valid, error = validate_markdown_text(payload)
            if not valid:
                raise ValueError(f"Invalid Markdown: {error}")
            self._client.add_comment(issue_key, payload)
            return f"Added markdown comment to {issue_key}"

        if not payload.strip():
            raise ValueError("Comment is empty")

        self._client.add_comment(issue_key, payload)
        return f"Added comment to {issue_key}"

    def ensure_loaded(self, issue_key: str) -> list[dict[str, Any]]:
        """Lazy-load comments for an issue and return current list."""
        if issue_key not in self._issue_comments:
            comments = self._client.get_issue_comments(issue_key)
            self._issue_comments[issue_key] = comments
            self._issue_comment_index[issue_key] = 0
        return self._issue_comments[issue_key]

    def invalidate_issue(self, issue_key: str) -> None:
        """Drop cached comments and index for one issue."""
        self._issue_comments.pop(issue_key, None)
        self._issue_comment_index.pop(issue_key, None)

    def next_comment(self, issue_key: str) -> bool:
        """Move comment pointer forward when possible."""
        comments = self.ensure_loaded(issue_key)
        if not comments:
            return False
        index = self._issue_comment_index.get(issue_key, 0)
        self._issue_comment_index[issue_key] = min(index + 1, len(comments) - 1)
        return True

    def prev_comment(self, issue_key: str) -> bool:
        """Move comment pointer backward when possible."""
        comments = self.ensure_loaded(issue_key)
        if not comments:
            return False
        index = self._issue_comment_index.get(issue_key, 0)
        self._issue_comment_index[issue_key] = max(index - 1, 0)
        return True

    def current_view(self, issue_key: str) -> tuple[str, str]:
        """Return current comment text and position label."""
        comments = self.ensure_loaded(issue_key)
        if not comments:
            return "[dim]No comments[/dim]", "0/0"

        index = self._issue_comment_index.get(issue_key, 0)
        index = max(index, 0)
        if index >= len(comments):
            index = len(comments) - 1
        self._issue_comment_index[issue_key] = index

        comment = comments[index]
        author = comment.get("author", {}).get("displayName", "unknown")
        created = str(comment.get("created", ""))[:19]
        text = self._extract_comment_text(comment)
        if len(text) > 280:
            text = f"{text[:277]}..."
        comment_text = f"[dim]@{author} {created}[/dim]\n{text}"
        return comment_text, f"{index + 1}/{len(comments)}"


    @staticmethod
    def _extract_comment_text(comment: dict[str, Any]) -> str:
        """Extract plain text summary from Jira comment body."""
        body = comment.get("body")
        if isinstance(body, str):
            return body
        if isinstance(body, dict):
            return json.dumps(body, ensure_ascii=False)
        return ""
