"""Textual roadmap-style timeline prototype."""

from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta

from rich.text import Text
from textual import events
from textual._context import NoActiveAppError
from textual.widgets import Static

from .model import TimelineGranularity, TimelineItem, TimelineMarker


class TimelineWidget(Static):
    """Render an Epic-first, expandable roadmap with a scrollable time grid."""

    can_focus = True
    GRANULARITIES: tuple[TimelineGranularity, ...] = ("auto", "week", "month", "quarter", "year")
    DEFAULT_CSS = """
    TimelineWidget {
        min-width: 90;
        height: 1fr;
        overflow-x: auto;
        overflow-y: auto;
    }
    """

    def __init__(
        self,
        items: list[TimelineItem] | None = None,
        markers: list[TimelineMarker] | None = None,
        granularity: TimelineGranularity = "auto",
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.items = items or []
        self.markers = markers or []
        self.granularity = granularity
        self.expanded_keys: set[str] = {item.key for item in self.items if item.is_epic}
        self._visible_rows: list[TimelineItem] = []

    def update_items(self, items: list[TimelineItem]) -> None:
        """Replace items while preserving expanded keys where possible."""
        self.items = items
        self.expanded_keys &= {item.key for item in items}
        self.expanded_keys |= {item.key for item in items if item.is_epic}
        self._refresh_render()

    def update_markers(self, markers: list[TimelineMarker]) -> None:
        """Replace versions or milestones shown on the timeline."""
        self.markers = markers
        self._refresh_render()

    def set_granularity(self, granularity: TimelineGranularity) -> None:
        """Change the time-axis granularity."""
        self.granularity = granularity
        self._refresh_render()

    def _refresh_render(self) -> None:
        """Refresh when mounted; keep model operations usable headlessly."""
        try:
            self.update(self.render())
        except NoActiveAppError:
            pass

    def on_key(self, event: events.Key) -> None:
        """Toggle Epics and cycle granularity inside the timeline."""
        if event.key in {"left_square_bracket", "right_square_bracket"}:
            index = self.GRANULARITIES.index(self.granularity)
            delta = -1 if event.key == "left_square_bracket" else 1
            self.set_granularity(self.GRANULARITIES[(index + delta) % len(self.GRANULARITIES)])
            event.stop()
            return
        if event.key not in {"space", "enter"} or not self._visible_rows:
            return
        index = min(self.cursor_line, len(self._visible_rows) - 1)
        item = self._visible_rows[index]
        if item.is_epic:
            if item.key in self.expanded_keys:
                self.expanded_keys.remove(item.key)
            else:
                self.expanded_keys.add(item.key)
            self.update(self.render())
            event.stop()

    def render(self) -> Text:
        dated = [item for item in self.items if item.is_scheduled]
        marker_dates = [marker.date for marker in self.markers]
        undated = [item for item in self.items if not item.is_scheduled]
        self._visible_rows = self._hierarchy(self.items)
        if not dated and not marker_dates:
            return Text("No dated planning items\n\n" + self._rows_without_dates(self._visible_rows))

        first = min([item.start for item in dated] + marker_dates)
        last = max([item.end for item in dated] + marker_dates)
        assert first is not None and last is not None
        unit = self._resolve_granularity(first, last)
        periods = self._periods(first, last, unit)
        cell_width = 12
        label_width = max(22, min(36, max(len(item.key) for item in self.items) + 2))
        lines: list[str | Text] = [f"Work item [{unit}]".ljust(label_width) + " " + "".join(f"{label:^{cell_width}}" for label, _ in periods)]
        lines.append(f"{'':<{label_width}} " + "".join("-" * cell_width for _ in periods))
        for marker in self.markers:
            lines.append(self._marker_line(marker, periods, unit, cell_width, label_width))
        for item in self._visible_rows:
            bar = self._bar(item, periods, unit, cell_width)
            indent = "  " if item.parent_key else ""
            marker = "v " if item.is_epic and item.key in self.expanded_keys else "> " if item.is_epic else "  "
            lines.append(f"{indent}{marker}{item.key:<{label_width - len(indent) - 2}} {bar} {item.title}")
        if undated:
            lines.extend(("", "Undated", self._rows_without_dates([item for item in self._visible_rows if not item.is_scheduled])))
        rendered = Text()
        for index, line in enumerate(lines):
            if index:
                rendered.append("\n")
            rendered.append_text(line if isinstance(line, Text) else Text(line))
        return rendered

    @classmethod
    def _marker_line(
        cls,
        marker: TimelineMarker,
        periods: list[tuple[str, date]],
        unit: str,
        cell_width: int,
        label_width: int,
    ) -> str:
        """Render a version/milestone as a colored horizontal line."""
        text = Text(f"◆ {marker.name:<{max(0, label_width - 2)}} ")
        for _, period in periods:
            period_end = cls._period_end(period, unit)
            text.append("─" * cell_width if marker.date <= period_end else " " * cell_width, style=marker.color)
        return text

    def _hierarchy(self, items: list[TimelineItem]) -> list[TimelineItem]:
        by_parent: dict[str, list[TimelineItem]] = {}
        keys = {item.key for item in items}
        for item in items:
            by_parent.setdefault(item.parent_key, []).append(item)
        roots = [item for item in items if not item.parent_key or item.parent_key not in keys]
        result: list[TimelineItem] = []

        def add(item: TimelineItem) -> None:
            result.append(item)
            if item.key in self.expanded_keys:
                for child in by_parent.get(item.key, []):
                    add(child)

        for root in roots:
            add(root)
        return result

    def _resolve_granularity(self, first: date, last: date) -> str:
        if self.granularity != "auto":
            return self.granularity
        days = (last - first).days
        return "week" if days <= 90 else "month" if days <= 730 else "quarter" if days <= 1825 else "year"

    @staticmethod
    def _periods(first: date, last: date, unit: str) -> list[tuple[str, date]]:
        periods: list[tuple[str, date]] = []
        cursor = first
        if unit == "week":
            cursor -= timedelta(days=cursor.weekday())
            step = lambda value: value + timedelta(days=7)
            label = lambda value: value.strftime("%d %b")
        elif unit == "month":
            cursor = cursor.replace(day=1)
            step = lambda value: value.replace(year=value.year + (value.month // 12), month=value.month % 12 + 1)
            label = lambda value: value.strftime("%b %Y")
        elif unit == "quarter":
            month = ((cursor.month - 1) // 3) * 3 + 1
            cursor = cursor.replace(month=month, day=1)
            step = lambda value: value.replace(year=value.year + ((value.month + 2) // 12), month=(value.month + 2) % 12 + 1)
            label = lambda value: f"Q{((value.month - 1) // 3) + 1} {value.year}"
        else:
            cursor = cursor.replace(month=1, day=1)
            step = lambda value: value.replace(year=value.year + 1)
            label = lambda value: str(value.year)
        while cursor <= last:
            periods.append((label(cursor), cursor))
            cursor = step(cursor)
        return periods

    @staticmethod
    def _bar(item: TimelineItem, periods: list[tuple[str, date]], unit: str, cell_width: int) -> str:
        if not item.is_scheduled:
            return " " * (len(periods) * cell_width)
        cells = []
        for _, period in periods:
            period_end = TimelineWidget._period_end(period, unit)
            cells.append("=" * cell_width if item.start <= period_end and item.end >= period else " " * cell_width)
        return "".join(cells)

    @staticmethod
    def _period_end(period: date, unit: str) -> date:
        if unit == "week":
            return period + timedelta(days=6)
        if unit == "month":
            return period.replace(day=monthrange(period.year, period.month)[1])
        if unit == "quarter":
            end_month = ((period.month - 1) // 3 + 1) * 3
            return period.replace(month=end_month, day=monthrange(period.year, end_month)[1])
        return period.replace(month=12, day=31)

    @staticmethod
    def _rows_without_dates(items: list[TimelineItem]) -> str:
        return "\n".join(f"{'  ' if item.parent_key else ''}{item.key} {item.title}" for item in items) or "(none)"
