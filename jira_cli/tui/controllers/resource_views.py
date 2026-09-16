"""User, label, and version resource views."""

from __future__ import annotations

from jira_cli.quick_filters import normalize_for_match
from jira_cli.tui.features.labels import LabelDetailWidget, LabelTableWidget, list_project_labels
from jira_cli.tui.features.users import UserDetailWidget, UserTableWidget, search_project_users
from jira_cli.tui.features.versions import VersionDetailWidget, VersionTableWidget, list_project_versions


class ResourceViewsMixin:
    """Load and display non-issue resources."""

    def _show_current_user(self) -> None:
        self._replace_users([self.client.get_current_user()], "Source: current user")

    def _show_assignable_users(self) -> None:
        users = sorted(
            self._load_mention_users(),
            key=lambda user: normalize_for_match(str(user.get("displayName") or user.get("accountId") or "")),
        )
        self._replace_users(users, f"Source: users in {self.project_key}")

    def action_toggle_theme(self) -> None:
        self.theme = "textual-light" if self.theme == "textual-dark" else "textual-dark"
        self.notify(f"Theme: {self.theme}")

    def _show_user_search(self, query: str) -> None:
        self._replace_users(search_project_users(self.client, self.project_key, query), f"Source: users matching '{query}'")

    def _show_versions(self, title: str) -> None:
        self._replace_versions(list_project_versions(self.client, self.project_key), f"Source: {title.lower()} in {self.project_key}")

    def _show_labels(self) -> None:
        self._replace_labels(list_project_labels(self.client, self.project_key), f"Source: labels in {self.project_key}")
        self._labels_loaded = True

    def _label_names(self) -> list[str]:
        if not self._labels_loaded:
            self.labels = list_project_labels(self.client, self.project_key)
            self._labels_loaded = True
        return [str(label.get("name", "")) for label in self.labels if label.get("name")]

    def _replace_users(self, users: list[dict], source_label: str) -> None:
        self.users = users
        selected = self.query_one("#user_table", UserTableWidget).replace_rows(users)
        self.query_one("#user_detail", UserDetailWidget).update_user(selected)
        self._show_resource("users")
        self.query_one("#query_context").update(source_label)

    def _replace_versions(self, versions: list[dict], source_label: str) -> None:
        self.versions = versions
        selected = self.query_one("#version_table", VersionTableWidget).replace_rows(versions)
        self.query_one("#version_detail", VersionDetailWidget).update_version(selected)
        self._show_resource("versions")
        self.query_one("#query_context").update(source_label)

    def _replace_labels(self, labels: list[dict], source_label: str) -> None:
        self.labels = labels
        selected = self.query_one("#label_table", LabelTableWidget).replace_rows(labels)
        self.query_one("#label_detail", LabelDetailWidget).update_label(selected)
        self._show_resource("labels")
        self.query_one("#query_context").update(source_label)
