"""Tests for the conflict-detection service."""

from datetime import datetime, timezone

from app.domain.models import Event
from app.services.conflicts import find_conflicts


def _make_event(start: datetime, end: datetime, title: str = "Existing") -> Event:
    return Event(title=title, start_time=start, end_time=end)


def test_no_overlap():
    """Events that don't overlap should not be returned as conflicts."""
    existing = [
        _make_event(
            datetime(2025, 1, 1, 8, 0, tzinfo=timezone.utc),
            datetime(2025, 1, 1, 9, 0, tzinfo=timezone.utc),
        ),
    ]
    conflicts = find_conflicts(
        new_start=datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
        new_end=datetime(2025, 1, 1, 11, 0, tzinfo=timezone.utc),
        existing_events=existing,
    )
    assert conflicts == []


def test_partial_overlap():
    """An event that partially overlaps should be returned as a conflict."""
    existing = [
        _make_event(
            datetime(2025, 1, 1, 9, 0, tzinfo=timezone.utc),
            datetime(2025, 1, 1, 10, 30, tzinfo=timezone.utc),
        ),
    ]
    conflicts = find_conflicts(
        new_start=datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
        new_end=datetime(2025, 1, 1, 11, 0, tzinfo=timezone.utc),
        existing_events=existing,
    )
    assert len(conflicts) == 1
    assert conflicts[0].start_time == datetime(2025, 1, 1, 9, 0, tzinfo=timezone.utc)


def test_exact_boundary_no_conflict():
    """When existing.end_time == new_start, there is no conflict (boundary touch)."""
    existing = [
        _make_event(
            datetime(2025, 1, 1, 9, 0, tzinfo=timezone.utc),
            datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
        ),
    ]
    conflicts = find_conflicts(
        new_start=datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
        new_end=datetime(2025, 1, 1, 11, 0, tzinfo=timezone.utc),
        existing_events=existing,
    )
    assert conflicts == []
