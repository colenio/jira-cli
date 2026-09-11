"""Output rendering (table, JSON, CSV, Markdown)."""

import csv
import io
import json
from typing import Any, Optional

from rich.console import Console
from rich.table import Table

from .models import IssueRow


def adf_to_text(node: Any) -> str:
    """Extract plain text from an Atlassian Document Format node/tree."""
    if not isinstance(node, dict):
        return str(node) if node else ""

    node_type = node.get("type")
    if node_type == "text":
        return str(node.get("text", ""))

    parts = [adf_to_text(child) for child in node.get("content", []) or []]
    text = "".join(parts)

    if node_type in {"paragraph", "heading", "codeBlock", "blockquote", "listItem"}:
        text += "\n"
    elif node_type == "hardBreak":
        text += "\n"

    return text


class JiraRenderer:
    """Render Jira data in multiple formats."""

    def __init__(self, console: Optional[Console] = None):
        self.console = console or Console()

    def table(self, rows: list[IssueRow], title: Optional[str] = None) -> None:
        """Render as rich table."""
        if not rows:
            self.console.print("[yellow]No issues found.[/yellow]")
            return

        t = Table(title=title)
        t.add_column("Key", style="cyan")
        t.add_column("Summary", style="white")
        t.add_column("Status", style="green")
        t.add_column("Priority", style="yellow")
        t.add_column("Assignee")
        t.add_column("Updated", style="dim")

        for row in rows:
            t.add_row(
                row.key,
                row.summary[:70] + "..." if len(row.summary) > 70 else row.summary,
                row.status,
                row.priority,
                row.assignee,
                row.updated[:10] if row.updated else "",
            )

        self.console.print(t)
        self.console.print(f"[green]✓ {len(rows)} issue(s)[/green]")

    def users_table(self, users: list[dict], title: Optional[str] = None) -> None:
        """Render a list of user dicts as a rich table (same style as `table()` for issues)."""
        if not users:
            self.console.print("[yellow]No users found.[/yellow]")
            return

        t = Table(title=title)
        t.add_column("Display Name", style="cyan")
        t.add_column("Email", style="white")
        t.add_column("Active", style="green")

        for user in users:
            active = "✓" if user.get("active") else "✗"
            t.add_row(user.get("displayName", "-"), user.get("emailAddress", "-"), active)

        self.console.print(t)
        self.console.print(f"[green]✓ {len(users)} user(s)[/green]")

    def versions_table(self, versions: list[dict], title: Optional[str] = None) -> None:
        """Render Jira fix versions/milestones as a rich table."""
        if not versions:
            self.console.print("[yellow]No versions found.[/yellow]")
            return

        t = Table(title=title)
        t.add_column("Name", style="cyan")
        t.add_column("Status", style="green")
        t.add_column("Release Date", style="yellow")

        for version in versions:
            state = "released" if version.get("released") else "unreleased"
            if version.get("archived"):
                state = f"{state}, archived"
            t.add_row(version.get("name", "-"), state, version.get("releaseDate") or "-")

        self.console.print(t)
        self.console.print(f"[green]✓ {len(versions)} version(s)[/green]")

    def json(self, rows: list[IssueRow]) -> str:
        """Render as JSON."""
        data = [row.model_dump() for row in rows]
        return json.dumps(data, indent=2)

    def csv(self, rows: list[IssueRow]) -> str:
        """Render as CSV."""
        if not rows:
            return ""

        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=rows[0].model_fields.keys())
        writer.writeheader()
        for row in rows:
            writer.writerow(row.model_dump())

        return output.getvalue()

    def markdown(self, rows: list[IssueRow]) -> str:
        """Render as Markdown table."""
        if not rows:
            return "No issues found.\n"

        lines = [
            "| Key | Summary | Status | Priority | Assignee |",
            "|-----|---------|--------|----------|----------|",
        ]

        for row in rows:
            summary = row.summary.replace("|", "\\|")[:70]
            lines.append(f"| {row.key} | {summary} | {row.status} | {row.priority} | {row.assignee} |")

        return "\n".join(lines) + "\n"

    def print(self, output: str) -> None:
        """Print raw output (for JSON/CSV/Markdown)."""
        self.console.print(output, highlight=False)
