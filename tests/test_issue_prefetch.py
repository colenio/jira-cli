"""Tests for lazy issue hierarchy loading."""

from jira_cli.models import IssueRow
from jira_cli.tui.features.issues.prefetch import IssueChildrenPrefetch


def test_prefetch_loads_children_for_github() -> None:
    issue = IssueRow(key="repo#42", summary="Parent")
    child = IssueRow(key="repo#43", summary="Child", parent_key="repo#42")
    applied = []

    class Query:
        def find_children(self, key: str, max_results: int = 50):
            assert key == "repo#42"
            assert max_results == 100
            return [child]

    selected = lambda: issue
    prefetch = IssueChildrenPrefetch(
        Query(),
        "github",
        lambda worker, **kwargs: worker(),
        lambda callback, *args: callback(*args),
        selected,
        applied.append,
    )

    prefetch.prefetch(issue)

    assert issue.children_loaded is True
    assert issue.child_keys == ["repo#43"]
    assert applied == [issue]


def test_prefetch_marks_issue_loaded_when_provider_fails() -> None:
    issue = IssueRow(key="#42", summary="Parent")

    class Query:
        def find_children(self, key: str, max_results: int = 50):
            raise RuntimeError("sub-issues unavailable")

    prefetch = IssueChildrenPrefetch(
        Query(),
        "github",
        lambda worker, **kwargs: worker(),
        lambda callback, *args: callback(*args),
        lambda: issue,
        lambda _: None,
    )

    prefetch.prefetch(issue)

    assert issue.children_loaded is True
    assert issue.child_keys == []
