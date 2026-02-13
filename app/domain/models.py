"""Domain models for the event lifecycle system."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class EventStatus(str, Enum):
    """Lifecycle status of a structured event."""

    DRAFT = "draft"
    CONFIRMED = "confirmed"
    REMINDED = "reminded"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class UnstructuredEvent(BaseModel):
    """Raw, free-text event input from a user."""

    raw_text: str


class StructuredEvent(BaseModel):
    """A parsed, structured representation of an event."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    start: datetime
    end: Optional[datetime] = None
    location: Optional[str] = None
    status: EventStatus = EventStatus.DRAFT
    raw_text: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Reminder(BaseModel):
    """A reminder associated with a structured event."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_id: str
    remind_at: datetime
    fired: bool = False
