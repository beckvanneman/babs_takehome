"""Domain models for the event lifecycle system."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field, model_validator

try:
    from enum import StrEnum
except ImportError:  # pragma: no cover - fallback for older Python runtimes

    class StrEnum(str, Enum):
        pass


class ParseResponseStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class EventStatus(StrEnum):
    DRAFT = "draft"
    CONFIRMED = "confirmed"
    CONFLICTED = "conflicted"
    CANCELLED = "cancelled"
    REMINDED = "reminded"


class TimelineEntryType(StrEnum):
    CREATED = "created"
    REMINDER_SCHEDULED = "reminder_scheduled"
    CONFLICT_DETECTED = "conflict_detected"
    SHARED = "shared"
    CONFIRMED = "confirmed"
    REMINDER_SENT = "reminder_sent"
    REJECTED = "rejected"


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
    status: EventStatus = EventStatus.DRAFT
    was_shared: bool = False
    reminders_scheduled: bool = False
    reminder_last_sent_at: datetime | None = None
    last_reminder_sent_id: str | None = None
    parent_event_id: str | None = None
    proposed_event_id: str | None = None
    recurrence_rule: str | None = None
    recurrence_end: datetime | None = None

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
    type: TimelineEntryType
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
    recurrence_description: str | None = None
    begin_recurrence: datetime | None = None
    end_recurrence_description: str | None = None

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
    id: str = Field(default_factory=_new_id)
    status: ParseResponseStatus = ParseResponseStatus.PENDING
    proposed_event: ProposedEvent
    ambiguities: list[Ambiguity] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    event_id: str | None = None


class ConfirmEventRequest(BaseModel):
    proposed_event: ProposedEvent


class ShareEventRequest(BaseModel):
    targets: list[str] = Field(min_length=1)
