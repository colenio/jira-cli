"""Provider-neutral timeline data for the first timeline prototype."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

TimelineGranularity = Literal["auto", "week", "month", "quarter", "year"]


@dataclass(frozen=True)
class TimelineItem:
    """An issue-like item with optional planning dates."""

    key: str
    title: str
    start: date | None = None
    end: date | None = None
    status: str = ""
    parent_key: str = ""
    issue_type: str = ""

    @property
    def is_scheduled(self) -> bool:
        """Return whether the item has a complete date range."""
        return self.start is not None and self.end is not None and self.end >= self.start

    @property
    def is_epic(self) -> bool:
        """Return whether the item is a top-level Epic row."""
        return self.issue_type.casefold() == "epic"


@dataclass(frozen=True)
class TimelineMarker:
    """A dated version or milestone displayed as a colored timeline line."""

    name: str
    date: date
    kind: str = "version"
    color: str = "cyan"
