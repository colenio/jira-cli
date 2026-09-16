"""Resource CRUD actions shared by the main TUI controller."""

from __future__ import annotations

from rich.markup import escape

from jira_cli.tui.features.issues.modals import EditIssueModal
from jira_cli.tui.features.labels import LabelTableWidget
from jira_cli.tui.features.labels.modals import LabelModal
from jira_cli.tui.features.versions import VersionTableWidget
from jira_cli.tui.features.versions.modals import VersionModal


class ResourceActionsMixin:
    """Handle issue, label, and version resource mutations."""

    def action_edit_resource(self) -> None:
        """Edit the selected item in the active resource view."""
        if self.active_kind == "labels":
            self._edit_selected_label()
            return
        if self.active_kind == "versions":
            self._edit_selected_version()
            return
        self.action_edit_title()

    def action_edit_title(self) -> None:
        """Open the common issue edit form."""
        issue = self._selected_issue()
        if not issue:
            self.notify("No issue selected", severity="warning")
            return

        self.pending_issue_key = issue.key
        self.push_screen(
            EditIssueModal(
                issue.key,
                issue.summary,
                description=issue.description,
                labels=issue.labels,
                label_candidates=self._label_names(),
            ),
            lambda fields: self.run_worker(self._submit_edit_fields(fields), exclusive=True) if fields else None,
        )

    def action_create_resource(self) -> None:
        """Open a create modal for the active resource."""
        if self.active_kind == "issues":
            repositories = self.client.list_issue_repositories() if hasattr(self.client, "list_issue_repositories") else []
            if self.context.provider == "github" and self.client.describe().supports_board and not repositories:
                self.notify("No repository is available for issue creation in this project", severity="warning")
                return
            self.push_screen(
                EditIssueModal(label_candidates=self._label_names(), repository_candidates=repositories),
                self._handle_new_issue_result,
            )
        elif self.active_kind == "labels":
            self.push_screen(LabelModal(), self._handle_label_result)
        elif self.active_kind == "versions":
            self.push_screen(VersionModal(), self._handle_version_result)

    def _handle_new_issue_result(self, result: dict | None) -> None:
        """Create a new issue from the common issue modal."""
        if not result or not result.get("summary"):
            return
        try:
            created = self.client.create_issue(
                self.project_key,
                result["summary"],
                body=result.get("description") or None,
                labels=result.get("labels") or None,
                repository=result.get("repository") or None,
            )
            self.notify(f"Created {created.get('key', 'issue')}")
            self.run_worker(self.action_refresh(), exclusive=True)
        except Exception as exc:
            self.notify(f"Issue creation failed: {escape(str(exc))}", severity="error")

    def action_delete_resource(self) -> None:
        """Open the selected resource in delete-ready edit mode."""
        if self.active_kind == "labels":
            self._edit_selected_label()
        elif self.active_kind == "versions":
            self._edit_selected_version()

    def _edit_selected_label(self) -> None:
        label = self.query_one("#label_table", LabelTableWidget).get_selected_label()
        if not label:
            self.notify("No label selected", severity="warning")
            return
        resource = self.client.describe().resource("labels")
        supports_metadata = bool(resource and "color" in resource.fields)
        self.push_screen(
            LabelModal(label, supports_metadata=supports_metadata, bulk=self.context.provider == "jira"),
            self._handle_label_result,
        )

    def _handle_label_result(self, result: dict | None) -> None:
        if not result:
            return
        try:
            if result["action"] == "create":
                self.client.create_label(self.project_key, result["name"], result["color"], result["description"])
            elif result["action"] == "edit":
                self.client.update_label(
                    self.project_key,
                    result["original_name"],
                    result["name"],
                    result["color"],
                    result["description"],
                )
            elif result["action"] == "delete":
                self.client.delete_label(self.project_key, result["name"])
            self._labels_loaded = False
            self._show_labels()
            self.notify("Labels updated")
        except Exception as exc:
            self.notify(f"Label update failed: {escape(str(exc))}", severity="error")

    def _edit_selected_version(self) -> None:
        version = self.query_one("#version_table", VersionTableWidget).get_selected_version()
        if not version:
            self.notify("No version selected", severity="warning")
            return
        self.push_screen(VersionModal(version), self._handle_version_result)

    def _handle_version_result(self, result: dict | None) -> None:
        if not result:
            return
        try:
            if result["action"] == "create":
                self.client.create_version(
                    self.project_key,
                    result["name"],
                    description=result["description"],
                    release_date=result["releaseDate"] or None,
                )
                if result["released"]:
                    self.client.update_version(self.project_key, result["name"], released=True)
            elif result["action"] == "edit":
                self.client.update_version(
                    self.project_key,
                    result["original_name"],
                    name=result["name"],
                    description=result["description"],
                    release_date=result["releaseDate"],
                    released=result["released"],
                )
            elif result["action"] == "delete":
                self.client.delete_version(self.project_key, result["name"])
            self._show_versions("Versions")
            self.notify("Versions updated")
        except Exception as exc:
            self.notify(f"Version update failed: {escape(str(exc))}", severity="error")
