"""Domain events emitted during the event lifecycle."""

from __future__ import annotations

from pydantic import BaseModel


class EventCreated(BaseModel):
    """Fired when a new StructuredEvent is persisted."""

    event_id: str


class EventStatusChanged(BaseModel):
    """Fired when an event transitions to a new lifecycle status."""

    event_id: str
    old_status: str
    new_status: str


class ReminderFired(BaseModel):
    """Fired when a reminder's time has been reached (via /tick)."""

    reminder_id: str
    event_id: str


class ConflictDetected(BaseModel):
    """Fired when a newly created event overlaps with an existing one."""

    event_id: str
    conflicting_event_id: str
