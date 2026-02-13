"""Domain event handlers — wired up at application startup."""

from __future__ import annotations

from app.domain.events import EventCreated


def on_event_created(event: EventCreated) -> None:
    """Placeholder: react to a newly created event (e.g. schedule reminders, check conflicts)."""
