"""View, capability, and input lifecycle actions for the TUI."""

from __future__ import annotations

from jira_cli.tui.features.board import BoardWidget
from jira_cli.tui.features.issues import IssueDetailWidget, IssueTableWidget
from jira_cli.tui.features.labels import LabelDetailWidget, LabelTableWidget
from jira_cli.tui.features.query.service import QUICK_FILTER_DIMENSIONS, build_query_labels
from jira_cli.tui.features.users import UserDetailWidget, UserTableWidget
from jira_cli.tui.features.versions import VersionDetailWidget, VersionTableWidget


class ViewControllerMixin:
    """Own resource visibility, capability checks, and input focus transitions."""

    def _update_query_context(self) -> None:
        """Render the active query and resource context."""
        mode_text, source_text = build_query_labels(
            self.project_key, self.query_mode, self.query_expression, self.query_language
        )
        if self.active_kind != "issues":
            mode_text = f"MODE: {self.active_kind.upper()}"
        for attribute, label in (
            ("type_filter", "TYPE"),
            ("status_filter", "STATUS"),
            ("assignee_filter", "ASSIGNEE"),
            ("label_filter", "LABEL"),
            ("priority_filter", "PRIORITY"),
            ("key_filter", "KEY"),
            ("order_by", "ORDER"),
        ):
            value = getattr(self, attribute)
            if value:
                mode_text = f"{mode_text} | {label}: {value}"
        self.query_one("#mode_context", object).update(mode_text)
        self.query_one("#query_context", object).update(source_text)

    def _show_resource(self, kind: str, board: bool = False) -> None:
        """Switch the central content area between resource kinds and issue board mode."""
        self.active_kind = kind
        self.board_visible = kind == "issues" and board
        self.query_one("#issue_table", IssueTableWidget).display = kind == "issues" and not board
        self.query_one("#issue_board", BoardWidget).display = kind == "issues" and board
        self.query_one("#issue_timeline").display = False
        self.timeline_visible = False
        self.query_one("#user_table", UserTableWidget).display = kind == "users"
        self.query_one("#version_table", VersionTableWidget).display = kind == "versions"
        self.query_one("#label_table", LabelTableWidget).display = kind == "labels"
        self.query_one("#issue_detail", IssueDetailWidget).display = kind == "issues"
        self.query_one("#user_detail", UserDetailWidget).display = kind == "users"
        self.query_one("#version_detail", VersionDetailWidget).display = kind == "versions"
        self.query_one("#label_detail", LabelDetailWidget).display = kind == "labels"

        if kind == "issues":
            if board:
                self.query_one("#issue_board", BoardWidget).focus()
            else:
                self.query_one("#issue_table", IssueTableWidget).focus()
        elif kind == "users":
            self.query_one("#user_table", UserTableWidget).focus()
        elif kind == "labels":
            self.query_one("#label_table", LabelTableWidget).focus()
        else:
            self.query_one("#version_table", VersionTableWidget).focus()
        self._update_query_context()
        self.refresh_bindings()
        self._update_issue_actions_bar()

    def _update_issue_actions_bar(self) -> None:
        """Show compact keyboard hints for selected issue actions."""
        toolbar = self.query_one("#issue_actions_bar", object)
        toolbar.display = self.active_kind == "issues" and not getattr(self, "timeline_visible", False)
        if not toolbar.display:
            return
        hints = []
        for key, action, label in (("t", "transition", "Transition"), ("a", "assign", "Assign"), ("e", "edit_resource", "Edit"), ("c", "comment", "Comment")):
            if self.check_action(action, ()):
                hints.append(f"[bold yellow]{key}[/bold yellow] {label}")
        hints.extend(("[bold yellow]u[/bold yellow] Parent", "[bold yellow]d[/bold yellow] Children"))
        if getattr(self, "timeline_visible", False):
            hints.append("[bold yellow]s[/bold yellow] Scale")
        self.query_one("#issue_actions_hint", object).update("  |  ".join(hints))

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        """Expose only actions that make sense for the active resource and provider."""
        issue_actions = {"focus_find", "toggle_board", "open_issue", "transition", "assign", "comment", "drill_up", "drill_down"}
        if action in issue_actions:
            return self.active_kind == "issues"
        if action == "edit_resource":
            if self.active_kind == "issues":
                return True
            return self.active_kind in {"labels", "versions"} and self._resource_supports_action(self.active_kind, "edit")
        if action == "create_resource":
            return self.active_kind in {"issues", "labels", "versions"} and self._resource_supports_action(self.active_kind, "create")
        if action == "delete_resource":
            return self.active_kind in {"labels", "versions"} and self._resource_supports_action(self.active_kind, "delete")
        if action == "issues_for_resource":
            return self.active_kind in {"labels", "versions", "users"}
        return True

    def _resource_supports_action(self, kind: str, action: str) -> bool:
        resource = self.client.describe().resource(kind)
        return bool(resource and any(item.name == action for item in resource.actions))

    def _command_verbs(self) -> list[str]:
        """Return command-palette verbs available in the current resource context."""
        verbs = ["users", "labels", "versions", "clear"]
        if self.active_kind == "issues":
            verbs.extend(["table", "board", "view", "create", "order=", *(f"{verb}=" for verb in QUICK_FILTER_DIMENSIONS)])
        elif self.active_kind == "users":
            verbs.append("user=")
        elif self.active_kind in {"labels", "versions"}:
            verbs.extend(["edit", "related"])
        for action in ("create", "edit", "delete"):
            action_name = f"{action}_resource" if action != "edit" else "edit_resource"
            if self.check_action(action_name, ()) and action not in verbs:
                verbs.append(action)
        return verbs

    def _restore_active_focus(self, preferred_key: str | None = None) -> None:
        """Return focus to the active main widget."""
        if self.active_kind == "issues":
            if self.board_visible:
                board = self.query_one("#issue_board", BoardWidget)
                selected = self._selected_issue()
                board.focus_board(preferred_key=preferred_key or (selected.key if selected else None))
            else:
                self.query_one("#issue_table", IssueTableWidget).focus()
        elif self.active_kind == "users":
            self.query_one("#user_table", UserTableWidget).focus()
        elif self.active_kind == "labels":
            self.query_one("#label_table", LabelTableWidget).focus()
        elif self.active_kind == "versions":
            self.query_one("#version_table", VersionTableWidget).focus()

    def _show_query_input(self, placeholder: str, value: str = "") -> None:
        query_input = self.query_one("#query_input", object)
        query_input.disabled = False
        query_input.placeholder = placeholder
        query_input.value = value
        query_input.display = True
        query_input.focus()

    def _hide_query_input(self) -> None:
        query_input = self.query_one("#query_input", object)
        query_input.display = False
        query_input.disabled = True
        self._restore_active_focus()

    def _show_filter_input(self) -> None:
        filter_input = self.query_one("#filter_input", object)
        filter_input.placeholder = {
            "issues": "Filter issues (key/summary/status/assignee)",
            "users": "Filter users by name/email; use 'me' for current user",
            "versions": "Filter versions/milestones by name/status/date",
            "labels": "Filter labels by name/description",
        }[self.active_kind]
        filter_input.disabled = False
        filter_input.display = True
        filter_input.focus()

    def _hide_filter_input(self) -> None:
        filter_input = self.query_one("#filter_input", object)
        filter_input.display = False
        filter_input.disabled = True
        filter_input.value = ""
        self._restore_active_focus()
