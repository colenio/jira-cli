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


def test_adf_comment_body_is_rendered_as_text():
    feature = JiraCommentFeature(CommentProvider())
    feature._issue_comments["COM-238"] = [
        {
            "author": {"displayName": "Marcel Körtgen"},
            "created": "2026-03-12T17:42:08",
            "body": {
                "type": "doc",
                "version": 1,
                "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Readable comment"}]}],
            },
        }
    ]

    thread = feature.thread_view("COM-238")

    assert "Readable comment" in thread
    assert '"type": "doc"' not in thread
