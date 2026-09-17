"""Tests for the timeline prototype."""

from datetime import date

from jira_cli.tui.features.timeline import TimelineItem, TimelineMarker, TimelineWidget


def test_timeline_renders_dated_items_and_undated_section() -> None:
    widget = TimelineWidget(
        [
            TimelineItem("A-1", "First", date(2026, 9, 1), date(2026, 9, 3), "To Do"),
            TimelineItem("A-2", "No dates"),
        ]
    )

    rendered = str(widget.render())

    assert "A-1" in rendered
    assert "First" in rendered
    assert "Undated" in rendered
    assert "A-2 No dates" in rendered


def test_timeline_without_dates_is_explicit() -> None:
    rendered = str(TimelineWidget([TimelineItem("A-1", "No dates")]).render())

    assert rendered == "No dated planning items\n\nA-1 No dates"


def test_timeline_groups_children_under_expanded_epic() -> None:
    widget = TimelineWidget(
        [
            TimelineItem("E-1", "Epic", date(2026, 9, 1), date(2026, 9, 30), issue_type="Epic"),
            TimelineItem("E-2", "Story", date(2026, 9, 5), date(2026, 9, 12), parent_key="E-1"),
        ]
    )

    rendered = str(widget.render())

    assert "v E-1" in rendered
    assert "E-2" in rendered


def test_timeline_granularity_can_be_changed() -> None:
    widget = TimelineWidget([TimelineItem("E-1", "Epic", date(2026, 1, 1), date(2026, 12, 31), issue_type="Epic")])

    widget.set_granularity("quarter")

    assert "Work item [quarter]" in str(widget.render())


def test_timeline_renders_colored_version_marker() -> None:
    widget = TimelineWidget(
        [TimelineItem("E-1", "Epic", date(2026, 9, 1), date(2026, 9, 30), issue_type="Epic")],
        markers=[TimelineMarker("v1.0", date(2026, 9, 15), color="cyan")],
    )

    rendered = widget.render()

    assert "v1.0" in rendered.plain
    assert "─" in rendered.plain
    assert any(span.style and "cyan" in str(span.style) for span in rendered.spans)
