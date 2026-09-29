"""Provider-neutral timeline contracts shared by adapters and the TUI."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

TimelineGranularity = Literal["auto", "sprint", "week", "month", "quarter", "year"]


@dataclass(frozen=True)
class TimelinePeriod:
    """A labeled interval on the timeline axis."""

    label: str
    start: date
    end: date
    state: str = ""
    id: str = ""


@dataclass(frozen=True)
class TimelineItem:
    """A provider-neutral planning item with optional dates and Sprint assignments."""

    key: str
    title: str
    start: date | None = None
    end: date | None = None
    status: str = ""
    parent_key: str = ""
    issue_type: str = ""
    sprint_ids: tuple[str, ...] = ()
    target_url: str = ""

    @property
    def is_scheduled(self) -> bool:
        """Return whether the item has a valid inclusive date range."""
        return self.start is not None and self.end is not None and self.end >= self.start


@dataclass(frozen=True)
class TimelineMarker:
    """A dated version or milestone displayed as a colored timeline marker."""

    name: str
    date: date
    kind: str = "version"
    color: str = "cyan"
