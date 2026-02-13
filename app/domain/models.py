"""Domain models for the event lifecycle system."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, Field, model_validator


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Core domain models
# ---------------------------------------------------------------------------


class Event(BaseModel):
    id: str = Field(default_factory=_new_id)
    title: str
    start_time: datetime
    end_time: datetime
    location: str | None = None
    notes: str | None = None
    created_at: datetime = Field(default_factory=_utcnow)
    is_confirmed: bool = False
    was_shared: bool = False
    reminders_scheduled: bool = False
    reminder_last_sent_at: datetime | None = None

    @model_validator(mode="after")
    def _end_after_start(self) -> Event:
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        return self


class ReminderPreference(BaseModel):
    id: str = Field(default_factory=_new_id)
    event_id: str
    offset_minutes: int = Field(gt=0)
    channel: str = "log"
    target: str | None = None


class ReminderScheduleItem(BaseModel):
    id: str = Field(default_factory=_new_id)
    event_id: str
    preference_id: str
    trigger_time: datetime
    channel: str
    target: str | None = None
    was_sent: bool = False
    sent_at: datetime | None = None


class TimelineEntry(BaseModel):
    id: str = Field(default_factory=_new_id)
    event_id: str
    timestamp: datetime = Field(default_factory=_utcnow)
    type: str
    payload: dict = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Request / Response DTOs
# ---------------------------------------------------------------------------


class ParseRequest(BaseModel):
    text: str


class ProposedEvent(BaseModel):
    title: str
    start_time: datetime
    end_time: datetime
    location: str | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def _end_after_start(self) -> ProposedEvent:
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        return self


class Ambiguity(BaseModel):
    field: str
    reason: str
    options: list[str] = Field(default_factory=list)


class ParseResponse(BaseModel):
    proposed_event: ProposedEvent
    ambiguities: list[Ambiguity] = Field(default_factory=list)


class CreateEventRequest(BaseModel):
    proposed_event: ProposedEvent
    reminder_offsets_minutes: list[int] | None = None

    @model_validator(mode="after")
    def _offsets_positive(self) -> CreateEventRequest:
        if self.reminder_offsets_minutes is not None:
            for offset in self.reminder_offsets_minutes:
                if offset <= 0:
                    raise ValueError("reminder offsets must be positive integers")
        return self


class CreateEventResponse(BaseModel):
    event: Event
    conflicts: list[Event] = Field(default_factory=list)
