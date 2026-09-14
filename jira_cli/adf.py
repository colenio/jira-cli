"""Markdown and Atlassian Document Format conversion helpers."""

from __future__ import annotations

from typing import Any

from md_adf import adf_to_markdown, markdown_to_adf


def adf_to_markdown_text(value: Any) -> str:
    """Convert ADF or plain text to Markdown, with a conservative text fallback."""
    if isinstance(value, str):
        return value
    if not isinstance(value, dict):
        return str(value) if value else ""
    try:
        result = adf_to_markdown(value)
        return result.value
    except Exception:
        return _adf_to_plain_text(value).strip()


def markdown_to_adf_document(value: str) -> dict[str, Any]:
    """Convert Markdown/plain text to a Jira-compatible ADF document."""
    result = markdown_to_adf(value)
    return result.value


def _adf_to_plain_text(node: Any) -> str:
    """Extract readable text when ADF conversion cannot handle a node."""
    if not isinstance(node, dict):
        return str(node) if node else ""
    if node.get("type") == "text":
        return str(node.get("text", ""))
    text = "".join(_adf_to_plain_text(child) for child in node.get("content", []) or [])
    if node.get("type") in {"paragraph", "heading", "codeBlock", "blockquote", "listItem", "hardBreak"}:
        text += "\n"
    return text
