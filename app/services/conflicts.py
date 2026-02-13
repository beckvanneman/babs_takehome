"""Service for detecting scheduling conflicts between events."""

from __future__ import annotations

from app.domain.models import StructuredEvent


def detect_conflicts(
    new_event: StructuredEvent,
    existing_events: list[StructuredEvent],
) -> list[StructuredEvent]:
    """Return any existing events that overlap with *new_event*.

    Currently a placeholder.
    """
    raise NotImplementedError("detect_conflicts is not yet implemented")
