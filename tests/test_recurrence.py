"""Tests for the recurrence compilation and expansion service."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.domain.models import Event, ProposedEvent
from app.services.recurrence import compile_rrule, expand_recurrence


# ---------------------------------------------------------------------------
# compile_rrule
# ---------------------------------------------------------------------------


def test_compile_weekly_thursday():
    proposed = ProposedEvent(
        title="Soccer practice",
        start_time=datetime(2026, 2, 19, 15, 30, tzinfo=timezone.utc),
        end_time=datetime(2026, 2, 19, 17, 0, tzinfo=timezone.utc),
        recurrence_description="every Thursday",
    )
    rule = compile_rrule(proposed)
    assert rule is not None
    assert "FREQ=WEEKLY" in rule
    assert "BYDAY=TH" in rule
    assert "INTERVAL" not in rule


def test_compile_every_other_thursday():
    proposed = ProposedEvent(
        title="Soccer practice",
        start_time=datetime(2026, 2, 19, 15, 30, tzinfo=timezone.utc),
        end_time=datetime(2026, 2, 19, 17, 0, tzinfo=timezone.utc),
        recurrence_description="every other Thursday",
    )
    rule = compile_rrule(proposed)
    assert rule is not None
    assert "FREQ=WEEKLY" in rule
    assert "INTERVAL=2" in rule
    assert "BYDAY=TH" in rule


def test_compile_daily():
    proposed = ProposedEvent(
        title="Standup",
        start_time=datetime(2026, 3, 1, 9, 0, tzinfo=timezone.utc),
        end_time=datetime(2026, 3, 1, 9, 15, tzinfo=timezone.utc),
        recurrence_description="daily",
    )
    rule = compile_rrule(proposed)
    assert rule is not None
    assert "FREQ=DAILY" in rule


def test_compile_returns_none_for_no_recurrence():
    proposed = ProposedEvent(
        title="One-off meeting",
        start_time=datetime(2026, 3, 1, 10, 0, tzinfo=timezone.utc),
        end_time=datetime(2026, 3, 1, 11, 0, tzinfo=timezone.utc),
    )
    assert compile_rrule(proposed) is None


def test_compile_weekdays():
    proposed = ProposedEvent(
        title="Morning run",
        start_time=datetime(2026, 3, 2, 7, 0, tzinfo=timezone.utc),
        end_time=datetime(2026, 3, 2, 8, 0, tzinfo=timezone.utc),
        recurrence_description="every weekday",
    )
    rule = compile_rrule(proposed)
    assert rule is not None
    assert "FREQ=WEEKLY" in rule
    for day in ("MO", "TU", "WE", "TH", "FR"):
        assert day in rule


# ---------------------------------------------------------------------------
# expand_recurrence
# ---------------------------------------------------------------------------


def test_expand_weekly_four_weeks():
    """A weekly event over ~4 weeks should produce 3 children (parent excluded)."""
    parent = Event(
        title="Soccer practice",
        start_time=datetime(2026, 2, 19, 15, 30, tzinfo=timezone.utc),
        end_time=datetime(2026, 2, 19, 17, 0, tzinfo=timezone.utc),
        recurrence_rule="FREQ=WEEKLY;BYDAY=TH",
        recurrence_end=datetime(2026, 3, 13, 23, 59, tzinfo=timezone.utc),
    )
    children = expand_recurrence(parent)

    assert len(children) == 3
    expected_dates = [
        datetime(2026, 2, 26, 15, 30, tzinfo=timezone.utc),
        datetime(2026, 3, 5, 15, 30, tzinfo=timezone.utc),
        datetime(2026, 3, 12, 15, 30, tzinfo=timezone.utc),
    ]
    for child, expected_start in zip(children, expected_dates):
        assert child.start_time == expected_start
        assert child.end_time == expected_start + timedelta(hours=1, minutes=30)
        assert child.parent_id == parent.id
        assert child.recurrence_rule is None
        assert child.title == "Soccer practice"
        assert child.location == parent.location


def test_expand_returns_empty_without_rule():
    parent = Event(
        title="One-off",
        start_time=datetime(2026, 3, 1, 10, 0, tzinfo=timezone.utc),
        end_time=datetime(2026, 3, 1, 11, 0, tzinfo=timezone.utc),
    )
    assert expand_recurrence(parent) == []


def test_expand_returns_empty_without_end():
    parent = Event(
        title="No end",
        start_time=datetime(2026, 3, 1, 10, 0, tzinfo=timezone.utc),
        end_time=datetime(2026, 3, 1, 11, 0, tzinfo=timezone.utc),
        recurrence_rule="FREQ=WEEKLY;BYDAY=MO",
    )
    assert expand_recurrence(parent) == []


def test_expand_biweekly():
    """Every other Thursday for 5 weeks → 2 children."""
    parent = Event(
        title="Biweekly sync",
        start_time=datetime(2026, 3, 5, 14, 0, tzinfo=timezone.utc),
        end_time=datetime(2026, 3, 5, 15, 0, tzinfo=timezone.utc),
        recurrence_rule="FREQ=WEEKLY;INTERVAL=2;BYDAY=TH",
        recurrence_end=datetime(2026, 4, 3, 23, 59, tzinfo=timezone.utc),
    )
    children = expand_recurrence(parent)

    assert len(children) == 2
    assert children[0].start_time == datetime(2026, 3, 19, 14, 0, tzinfo=timezone.utc)
    assert children[1].start_time == datetime(2026, 4, 2, 14, 0, tzinfo=timezone.utc)
