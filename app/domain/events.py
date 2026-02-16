"""Domain events emitted during the event lifecycle."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class EventCreated(BaseModel):
    """Fired when a new Event is persisted."""

    event_id: str
    reminder_offsets_minutes: list[int] | None = None


class EventShared(BaseModel):
    """Fired when an event is shared with other people."""

    event_id: str
    targets: list[str]


class ReminderScheduled(BaseModel):
    """Fired after reminders have been created for an event."""

    event_id: str
    schedule_item_ids: list[str]


class ReminderSent(BaseModel):
    """Fired when a reminder's time has been reached (via /tick)."""

    event_id: str
    schedule_item_id: str
    sent_at: datetime


class ConflictDetected(BaseModel):
    """Fired when a newly created event overlaps with existing ones."""

    event_id: str
    conflicting_event_ids: list[str]


class EventConfirmed(BaseModel):
    """Fired when an event is (re-)confirmed by a human."""

    event_id: str
