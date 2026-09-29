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

from .model import TimelineGranularity, TimelineItem, TimelineMarker, TimelinePeriod


class TimelineWidget(Vertical):
    """Show provider-neutral planning items and colored intervals in one table."""

    DEFAULT_CSS = """
    TimelineWidget { height: 1fr; width: 1fr; }
    #timeline_scale { height: 1; color: $accent; padding: 0 1; }
    #timeline_table { height: 1fr; width: 1fr; min-width: 110; overflow-x: auto; overflow-y: auto; }
    """

    COLORS = ("cyan", "green", "yellow", "magenta", "blue")
    BAR_WIDTH = 10
    VERSIONS_ROW_KEY = "__versions__"
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
        self.plan_items: list[TimelineItem] = []
        self.sprints: list[dict] = []
        self._periods: list[TimelinePeriod] = []
        self._unit = "month"
        self._period_width = self.BAR_WIDTH
        self._row_keys: list[str] = []

    def compose(self) -> ComposeResult:
        yield Static(id="timeline_scale")
        yield DataTable(fixed_columns=2, cursor_type="row", id="timeline_table")

    def on_mount(self) -> None:
        self._refresh()

    def update_items(self, items: list[TimelineItem]) -> None:
        """Replace the issue source and keep only chronologically sorted Epics."""
        self.items = items
        self._refresh()

    def focus_first_epic(self) -> None:
        """Focus the Epic table and select its first row."""
        table = self.query_one("#timeline_table", DataTable)
        if self.plan_items:
            table.move_cursor(row=0, column=0)
            table.focus()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Navigate to a selected Epic; Versions is informational only."""
        table = self.query_one("#timeline_table", DataTable)
        if 0 <= table.cursor_row < len(self._row_keys):
            key = self._row_keys[table.cursor_row]
            if key != self.VERSIONS_ROW_KEY:
                self.post_message(self.IssueSelected(key))

    def update_markers(self, markers: list[TimelineMarker]) -> None:
        """Replace versions or milestones shown in the timeline columns."""
        self.markers = markers
        self._refresh()

    def update_sprints(self, sprints: list[dict]) -> None:
        """Replace provider-derived sprint intervals on the timeline axis."""
        self.sprints = sprints
        self._refresh()

    def set_granularity(self, granularity: TimelineGranularity) -> None:
        """Change the time-axis granularity."""
        self.granularity = granularity
        self._refresh()

    def action_cycle_granularity(self) -> None:
        """Cycle through granularities and refresh the table."""
        values: tuple[TimelineGranularity, ...] = ("auto", "week", "month", "quarter", "year", "sprint")
        index = values.index(self.granularity)
        self.set_granularity(values[(index + 1) % len(values)])

    def _refresh(self) -> None:
        self.plan_items = sorted(
            self.items,
            key=lambda item: (item.start is None, item.start or date.max, item.key),
        )
        dated = [item for item in self.plan_items if item.is_scheduled]
        sprint_periods = self._sprint_periods_for(self.plan_items, [marker.date for marker in self.markers])
        if sprint_periods and self.granularity in ("auto", "sprint"):
            self._unit = "sprint"
            self._periods = sprint_periods
            self._period_width = min(28, max(self.BAR_WIDTH, max(len(period.label) for period in sprint_periods)))
        else:
            self._unit = self._resolve_granularity_for_items(dated)
            self._periods = self._periods_for(dated, self._unit, [marker.date for marker in self.markers])
            self._period_width = self.BAR_WIDTH
        try:
            table = self.query_one("#timeline_table", DataTable)
            table.clear(columns=True)
            self._row_keys = []
            labels = [period.label for period in self._periods]
            table.add_column("Plan", width=14)
            table.add_column("Title", width=42)
            for label in labels:
                table.add_column(label, width=self._period_width)
            for index, item in enumerate(self.plan_items):
                color = self.COLORS[index % len(self.COLORS)]
                cells = self._bar_cells(item, self._periods, color)
                table.add_row(
                    f"{item.issue_type or 'Plan'} {item.key}",
                    item.title,
                    *cells,
                    key=item.key,
                )
                self._row_keys.append(item.key)
            if self.markers and self._periods:
                marker_cells = self._marker_cells(self.markers, self._periods)
                table.add_row(
                    "",
                    Text("Versions", style="dim"),
                    *marker_cells,
                    height=max(1, self._marker_row_height(self.markers, self._periods)),
                    key=self.VERSIONS_ROW_KEY,
                )
                self._row_keys.append(self.VERSIONS_ROW_KEY)
            if not self.plan_items:
                table.add_row("", "No plan items with planning dates", *([""] * len(self._periods)))
            self._align_today(table, self._periods, self._period_width)
            self.query_one("#timeline_scale", Static).update(
                f"Scale: {self._unit} | s: scale | Enter: open | today: {date.today().isoformat()}"
            )
        except Exception:
            self.log.exception("Failed to refresh timeline table")

    def _resolve_granularity(self, first: date, last: date) -> str:
        if self.granularity not in ("auto", "sprint"):
            return self.granularity
        days = (last - first).days
        return "week" if days <= 90 else "month" if days <= 730 else "quarter" if days <= 1825 else "year"

    def _resolve_granularity_for_items(self, items: list[TimelineItem]) -> str:
        if self.granularity not in ("auto", "sprint"):
            return self.granularity
        if not items:
            return "month"
        return self._resolve_granularity(min(item.start for item in items), max(item.end for item in items))

    def _periods_for(self, items: list[TimelineItem], unit: str, marker_dates: list[date]) -> list[TimelinePeriod]:
        if not items and not marker_dates:
            return []
        starts = [item.start for item in items] + marker_dates
        ends = [item.end for item in items] + marker_dates
        starts.append(date.today())
        ends.append(date.today())
        first = min(starts)
        last = max(ends)
        assert first is not None and last is not None
        return [TimelinePeriod(label, start, self._period_end(start, unit)) for label, start in self._periods_between(first, last, unit)]

    def _sprint_periods_for(self, items: list[TimelineItem], marker_dates: list[date]) -> list[TimelinePeriod]:
        """Build timeline columns from dated provider sprints overlapping the plan window."""
        if not self.sprints:
            return []
        periods = []
        assigned_sprint_ids = {sprint_id for item in items for sprint_id in item.sprint_ids}
        for sprint in self.sprints:
            try:
                start = date.fromisoformat(str(sprint.get("startDate", ""))[:10])
                end = date.fromisoformat(str(sprint.get("endDate", ""))[:10])
            except ValueError:
                continue
            if end < start:
                continue
            name = str(sprint.get("name") or "Sprint")
            board = str(sprint.get("board") or "")
            sprint_id = str(sprint.get("id") or sprint.get("sprintId") or "")
            periods.append(
                TimelinePeriod(
                    f"{name} ({board})" if board else name,
                    start,
                    end,
                    str(sprint.get("state") or ""),
                    sprint_id,
                )
            )
        if not periods:
            return []

        plan_dates = [value for item in items for value in (item.start, item.end) if value is not None]
        plan_dates.extend(marker_dates)
        plan_dates.append(date.today())
        first, last = min(plan_dates), max(plan_dates)
        return sorted(
            (
                period
                for period in periods
                if period.id in assigned_sprint_ids or (period.end >= first and period.start <= last)
            ),
            key=lambda period: (period.start, period.end, period.label),
        )

    def _bar_cells(self, item: TimelineItem, periods: list[TimelinePeriod], color: str) -> list[Text]:
        cells = []
        for period in periods:
            if self._unit == "sprint" and item.sprint_ids:
                active = period.id in item.sprint_ids
            else:
                active = item.start is not None and item.end is not None and item.start <= period.end and item.end >= period.start
            cells.append(Text("=" * self.BAR_WIDTH if active else "", style=color if active else None))
        return cells

    def _marker_cells(self, markers: list[TimelineMarker], periods: list[TimelinePeriod]) -> list[Text]:
        cells = []
        for period in periods:
            matches = [marker for marker in markers if period.end >= marker.date >= period.start]
            text = Text()
            for index, marker in enumerate(matches):
                if index:
                    text.append("\n")
                text.append(f"◆ {self._short_marker_name(marker.name)}", style=marker.color)
            cells.append(text)
        return cells

    def _marker_row_height(self, markers: list[TimelineMarker], periods: list[TimelinePeriod]) -> int:
        """Return the number of lines required by coincident version markers."""
        return max(
            (sum(period.end >= marker.date >= period.start for marker in markers) for period in periods),
            default=1,
        )

    @staticmethod
    def _short_marker_name(name: str, width: int = 8) -> str:
        """Keep marker labels within the fixed timeline cell width."""
        compact = name.strip()
        return compact if len(compact) <= width else f"{compact[:width - 1]}…"

    @staticmethod
    def _align_today(table: DataTable, periods: list[TimelinePeriod], period_width: int) -> None:
        """Scroll the time columns so today's period is visible near the viewport start."""
        today = date.today()
        for index, period in enumerate(periods):
            if period.start <= today <= period.end:
                table.scroll_to(x=max(0, (index - 1) * period_width), animate=False, immediate=True)
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
