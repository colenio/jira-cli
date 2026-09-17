"""Epic timeline table with chronological rows and an aligned axis footer."""

from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.message import Message
from textual.widgets import DataTable, Static

from .model import TimelineGranularity, TimelineItem, TimelineMarker


class TimelineWidget(Vertical):
    """Show Epic key/title and a colored timeline bar in one synchronized table."""

    DEFAULT_CSS = """
    TimelineWidget { height: 1fr; width: 1fr; }
    #timeline_scale { height: 1; color: $accent; padding: 0 1; }
    #timeline_table { height: 1fr; width: 1fr; min-width: 110; overflow-x: auto; overflow-y: auto; }
    """

    COLORS = ("cyan", "green", "yellow", "magenta", "blue")
    BAR_WIDTH = 10
    BINDINGS = [
        Binding("s", "cycle_granularity", "Scale", show=False),
    ]

    class IssueSelected(Message):
        """Request navigation to the selected issue in the main issue view."""

        def __init__(self, key: str) -> None:
            super().__init__()
            self.key = key

    def __init__(self, items: list[TimelineItem] | None = None, granularity: TimelineGranularity = "auto", **kwargs) -> None:
        super().__init__(**kwargs)
        self.items = items or []
        self.markers: list[TimelineMarker] = []
        self.granularity = granularity
        self.epics: list[TimelineItem] = []
        self._periods: list[tuple[str, date]] = []
        self._unit = "month"

    def compose(self) -> ComposeResult:
        yield Static(id="timeline_scale")
        yield DataTable(fixed_columns=2, cursor_type="row", id="timeline_table")

    def on_mount(self) -> None:
        self._refresh()

    def update_items(self, items: list[TimelineItem]) -> None:
        """Replace the issue source and keep only chronologically sorted Epics."""
        self.items = items
        self._refresh()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Navigate to the selected Epic or child issue with Enter."""
        rows = self._visible_rows()
        table = self.query_one("#timeline_table", DataTable)
        if 0 <= table.cursor_row < len(rows):
            self.post_message(self.IssueSelected(rows[table.cursor_row].key))

    def update_markers(self, markers: list[TimelineMarker]) -> None:
        """Replace versions or milestones shown in the timeline columns."""
        self.markers = markers
        self._refresh()

    def set_granularity(self, granularity: TimelineGranularity) -> None:
        """Change the time-axis granularity."""
        self.granularity = granularity
        self._refresh()

    def action_cycle_granularity(self) -> None:
        """Cycle through granularities and refresh the table."""
        values: tuple[TimelineGranularity, ...] = ("auto", "week", "month", "quarter", "year")
        index = values.index(self.granularity)
        self.set_granularity(values[(index + 1) % len(values)])

    def _refresh(self) -> None:
        self.epics = sorted(
            (item for item in self.items if item.is_epic),
            key=lambda item: (item.start is None, item.start or date.max, item.key),
        )
        dated = [item for item in self.epics if item.is_scheduled]
        self._unit = self._resolve_granularity_for_items(dated)
        self._periods = self._periods_for(dated, self._unit, [marker.date for marker in self.markers])
        try:
            table = self.query_one("#timeline_table", DataTable)
            table.clear(columns=True)
            labels = [label for label, _ in self._periods]
            table.add_column("Epic", width=14)
            table.add_column("Title", width=42)
            for label in labels:
                table.add_column(label, width=self.BAR_WIDTH)
            for index, epic in enumerate(self.epics):
                color = self.COLORS[index % len(self.COLORS)] if epic.is_epic else "bright_black"
                cells = self._bar_cells(epic, self._periods, self._unit, color)
                table.add_row(
                    f"{'  ' if epic.parent_key else ''}{epic.issue_type_emoji} {epic.key}",
                    f"{'  ' if epic.parent_key else ''}{epic.title}",
                    *cells,
                    key=epic.key,
                )
            if self.markers and self._periods:
                table.add_row("", "Versions", *self._marker_cells(self.markers, self._periods, self._unit), key="__versions__")
            if not self.epics:
                table.add_row("", "No Epics with planning dates", *([""] * len(self._periods)))
            self._align_today(table, self._periods, self._unit)
            self.query_one("#timeline_scale", Static).update(
                f"Scale: {self._unit} | s: scale | Enter: open | today: {date.today().isoformat()}"
            )
        except Exception:
            pass


    def _resolve_granularity(self, first: date, last: date) -> str:
        if self.granularity != "auto":
            return self.granularity
        days = (last - first).days
        return "week" if days <= 90 else "month" if days <= 730 else "quarter" if days <= 1825 else "year"

    def _resolve_granularity_for_items(self, items: list[TimelineItem]) -> str:
        if self.granularity != "auto":
            return self.granularity
        if not items:
            return "month"
        return self._resolve_granularity(min(item.start for item in items), max(item.end for item in items))

    def _periods_for(self, items: list[TimelineItem], unit: str, marker_dates: list[date]) -> list[tuple[str, date]]:
        if not items and not marker_dates:
            return []
        starts = [item.start for item in items] + marker_dates
        ends = [item.end for item in items] + marker_dates
        starts.append(date.today())
        ends.append(date.today())
        first = min(starts)
        last = max(ends)
        assert first is not None and last is not None
        if self.granularity == "auto":
            first = self._period_start(date.today(), unit)
        return self._periods_between(first, last, unit)

    def _bar_cells(self, item: TimelineItem, periods: list[tuple[str, date]], unit: str, color: str) -> list[Text]:
        cells = []
        for _, period in periods:
            end = self._period_end(period, unit)
            active = item.start <= end and item.end >= period
            cells.append(Text("=" * self.BAR_WIDTH if active else "", style=color if active else None))
        return cells

    def _marker_cells(self, markers: list[TimelineMarker], periods: list[tuple[str, date]], unit: str) -> list[Text]:
        cells = []
        for _, period in periods:
            matches = [marker for marker in markers if self._period_end(period, unit) >= marker.date >= period]
            text = Text()
            for index, marker in enumerate(matches):
                if index:
                    text.append("\n")
                text.append(f"◆ {self._short_marker_name(marker.name)}", style=marker.color)
            cells.append(text)
        return cells

    @staticmethod
    def _short_marker_name(name: str, width: int = 8) -> str:
        """Keep marker labels within the fixed timeline cell width."""
        compact = name.strip()
        return compact if len(compact) <= width else f"{compact[:width - 1]}…"

    @staticmethod
    def _align_today(table: DataTable, periods: list[tuple[str, date]], unit: str) -> None:
        """Scroll the time columns so today's period is visible near the viewport start."""
        today = date.today()
        for index, (_, period) in enumerate(periods):
            if period <= today <= TimelineWidget._period_end(period, unit):
                table.scroll_to(x=max(0, (index - 1) * TimelineWidget.BAR_WIDTH), animate=False, immediate=True)
                return

    @staticmethod
    def _periods_between(first: date, last: date, unit: str) -> list[tuple[str, date]]:
        periods: list[tuple[str, date]] = []
        cursor = first
        if unit == "week":
            cursor -= timedelta(days=cursor.weekday()); step = lambda value: value + timedelta(days=7); label = lambda value: value.strftime("%d %b")
        elif unit == "month":
            cursor = cursor.replace(day=1); step = lambda value: value.replace(year=value.year + value.month // 12, month=value.month % 12 + 1); label = lambda value: value.strftime("%b %Y")
        elif unit == "quarter":
            cursor = cursor.replace(month=((cursor.month - 1) // 3) * 3 + 1, day=1); step = lambda value: value.replace(year=value.year + (value.month + 2) // 12, month=(value.month + 2) % 12 + 1); label = lambda value: f"Q{(value.month - 1) // 3 + 1} {value.year}"
        else:
            cursor = cursor.replace(month=1, day=1); step = lambda value: value.replace(year=value.year + 1); label = lambda value: str(value.year)
        while cursor <= last:
            periods.append((label(cursor), cursor)); cursor = step(cursor)
        return periods

    @staticmethod
    def _period_end(period: date, unit: str) -> date:
        if unit == "week": return period + timedelta(days=6)
        if unit == "month": return period.replace(day=monthrange(period.year, period.month)[1])
        if unit == "quarter":
            month = ((period.month - 1) // 3 + 1) * 3
            return period.replace(month=month, day=monthrange(period.year, month)[1])
        return period.replace(month=12, day=31)

    @staticmethod
    def _period_start(value: date, unit: str) -> date:
        """Return the first date of the current time period."""
        if unit == "week":
            return value - timedelta(days=value.weekday())
        if unit == "month":
            return value.replace(day=1)
        if unit == "quarter":
            return value.replace(month=((value.month - 1) // 3) * 3 + 1, day=1)
        return value.replace(month=1, day=1)
