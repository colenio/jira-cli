"""Background loading for issue hierarchy data."""

from __future__ import annotations

from collections.abc import Callable

from jira_cli.models import IssueRow


class IssueChildrenPrefetch:
    """Load child issues lazily and apply results only to the selected row."""

    def __init__(
        self,
        query,
        provider: str,
        run_worker: Callable,
        call_from_thread: Callable,
        selected_issue: Callable[[], IssueRow | None],
        update_detail: Callable[[IssueRow], None],
    ) -> None:
        self.query = query
        self.provider = provider
        self.run_worker = run_worker
        self.call_from_thread = call_from_thread
        self.selected_issue = selected_issue
        self.update_detail = update_detail
        self._cache: dict[str, list[str]] = {}

    def prefetch(self, issue: IssueRow) -> None:
        """Start loading children unless this issue is already resolved."""
        if issue.key in self._cache:
            return
        if issue.child_keys:
            self._cache[issue.key] = list(issue.child_keys)
            issue.children_loaded = True
            return

        def load_children() -> None:
            try:
                children = self.query.find_children(issue.key, max_results=100)
                self._cache[issue.key] = [child.key for child in children]
            except Exception:
                self._cache[issue.key] = []
            issue.child_keys = self._cache[issue.key]
            issue.children_loaded = True
            self.call_from_thread(self._apply_if_selected, issue.key, issue)

        self.run_worker(load_children, group="children-prefetch", exclusive=False, thread=True, exit_on_error=False)

    def _apply_if_selected(self, issue_key: str, loaded_issue: IssueRow) -> None:
        """Apply a result only when the original row is still selected."""
        issue = self.selected_issue()
        if issue is loaded_issue and issue.key == issue_key:
            self.update_detail(issue)
