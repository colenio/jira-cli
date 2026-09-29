"""Generic table widget for provider-declared catalog resources."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import DataTable, Markdown


class ProviderResourceTable(DataTable):
    """Render provider-specific resource records from descriptor fields."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.resource_kind = ""
        self.fields: tuple[str, ...] = ()
        self.resource_rows: list[dict[str, Any]] = []
        self.cursor_type = "row"

    def replace_resource(self, kind: str, fields: Sequence[str], rows: list[dict[str, Any]]) -> None:
        """Replace the catalog and build columns from its provider descriptor."""
        self.resource_kind = kind
        self.fields = tuple(fields)
        self.resource_rows = rows
        self.clear(columns=True)
        self.add_columns(*self.fields)
        for index, row in enumerate(rows):
            values = [self._cell_text(row.get(field)) for field in self.fields]
            key = str(row.get("id") or row.get("key") or row.get("name") or index)
            self.add_row(*values, key=key)
        if rows:
            self.move_cursor(row=0)

    @staticmethod
    def _cell_text(value: Any) -> str:
        if value is None or value == "":
            return "—"
        if isinstance(value, list):
            return ", ".join(ProviderResourceTable._cell_text(item) for item in value)
        if isinstance(value, dict):
            for key in ("name", "displayName", "value", "key", "id"):
                if value.get(key) not in (None, ""):
                    return str(value[key])
            return str(value)
        return str(value)


class ProviderResourceDetail(VerticalScroll):
    """Display the selected provider resource beside its catalog table."""

    DEFAULT_CSS = """
    ProviderResourceDetail {
        border: solid $accent;
        height: 1fr;
        padding: 0 1;
        color: $text;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.resource: dict[str, Any] | None = None
        self.fields: tuple[str, ...] = ()

    def compose(self) -> ComposeResult:
        yield Markdown(self._render_content(), open_links=False, id="provider_resource_detail_body")

    def update_resource(self, resource: dict[str, Any] | None, fields: Sequence[str] = ()) -> None:
        """Replace the displayed resource and its descriptor fields."""
        self.resource = resource
        self.fields = tuple(fields)
        self.query_one("#provider_resource_detail_body", Markdown).update(self._render_content())

    def _render_content(self) -> str:
        if self.resource is None:
            return "Select a row to view details"

        title = next(
            (self.resource.get(field) for field in ("name", "key", "title") if self.resource.get(field)),
            "Resource details",
        )
        lines = [str(title)]
        for field in self.fields:
            lines.extend(("", field, ProviderResourceTable._cell_text(self.resource.get(field))))
        return "\n".join(lines)
