"""Tests for comment format inference."""

from jira_cli.tui.features.comment.service import JiraCommentFeature


class CommentProvider:
    def add_comment(self, key, body, use_adf=False):
        return {}


def test_comment_format_is_inferred_without_prefixes():
    feature = JiraCommentFeature(CommentProvider())

    assert feature.normalize_input("This is **bold**") == ("md", "This is **bold**")
    assert feature.normalize_input("Use `jira tui`") == ("md", "Use `jira tui`")
    assert feature.normalize_input('{"type":"doc","version":1,"content":[]}')[0] == "adf"
    assert feature.normalize_input("A normal comment") == ("plain", "A normal comment")


def test_explicit_comment_prefixes_remain_supported():
    feature = JiraCommentFeature(CommentProvider())

    assert feature.normalize_input("plain:hello") == ("plain", "hello")
    assert feature.normalize_input("md:**hello**") == ("md", "**hello**")
