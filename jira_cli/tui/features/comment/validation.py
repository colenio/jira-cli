"""Comment format validators for Jira TUI."""

from typing import Any


def validate_markdown_text(text: str) -> tuple[bool, str]:
    """Perform lightweight markdown validation."""
    if not text.strip():
        return False, "Markdown text is empty"
    if text.count("```") % 2 != 0:
        return False, "Unclosed fenced code block detected"
    return True, ""


def _validate_adf_node(node: Any) -> tuple[bool, str]:
    """Validate a subset of ADF node shape recursively."""
    if not isinstance(node, dict):
        return False, "ADF node must be an object"

    node_type = node.get("type")
    if not isinstance(node_type, str) or not node_type:
        return False, "ADF node.type must be a non-empty string"

    if node_type == "text" and not isinstance(node.get("text"), str):
        return False, "ADF text node must include string field 'text'"

    content = node.get("content")
    if content is not None:
        if not isinstance(content, list):
            return False, "ADF node.content must be an array"
        for child in content:
            ok, error = _validate_adf_node(child)
            if not ok:
                return ok, error

    return True, ""


def validate_adf_doc(adf_doc: Any) -> tuple[bool, str]:
    """Validate minimal ADF document structure."""
    if not isinstance(adf_doc, dict):
        return False, "ADF must be a JSON object"
    if adf_doc.get("type") != "doc":
        return False, "ADF root type must be 'doc'"
    if adf_doc.get("version") != 1:
        return False, "ADF version must be 1"
    content = adf_doc.get("content")
    if not isinstance(content, list):
        return False, "ADF doc.content must be an array"
    for node in content:
        ok, error = _validate_adf_node(node)
        if not ok:
            return ok, error
    return True, ""
