"""Service for detecting scheduling conflicts between events."""

from __future__ import annotations

from datetime import datetime

from app.domain.models import Event


def find_conflicts(
    new_start: datetime,
    new_end: datetime,
    existing_events: list[Event],
) -> list[Event]:
    """Return existing events that overlap with the given time range.

    Overlap rule: conflict if new_start < existing.end_time AND existing.start_time < new_end.
    Exact boundary touches (end == start) are NOT considered conflicts.
    """
    return [
        event
        for event in existing_events
        if new_start < event.end_time and event.start_time < new_end
    ]
