"""FastAPI application — entry point for the event lifecycle service."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException

from app.domain.bus import EventBus
from app.domain.models import Event, ParseRequest, ParseResponse
from app.repos.memory import EventRepository, ReminderScheduleRepository
from app.services.parser import parse_unstructured_event

app = FastAPI(title="Event Lifecycle Service")

# ── Singletons (created at import time for simplicity) ────────────────
event_bus = EventBus()
event_repo = EventRepository()
reminder_repo = ReminderScheduleRepository()


# ── Routes ────────────────────────────────────────────────────────────


@app.post("/parse", response_model=ParseResponse)
def parse_event(payload: ParseRequest) -> ParseResponse:
    """Accept free-text and return a proposed event with any ambiguities."""
    now = datetime.now(timezone.utc)
    proposed_event, ambiguities = parse_unstructured_event(payload.text, now)
    return ParseResponse(proposed_event=proposed_event, ambiguities=ambiguities)


@app.get("/events", response_model=list[Event])
def list_events() -> list[Event]:
    """Return all stored events."""
    return event_repo.list_all()


@app.get("/events/{event_id}", response_model=Event)
def get_event(event_id: str) -> Event:
    """Return a single event by id."""
    event = event_repo.get(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


@app.post("/tick")
def tick(now: Optional[datetime] = None) -> dict:
    """Advance simulated time and fire any due reminders.

    Pass *now* as a query/body param to control the simulated clock.
    Defaults to ``datetime.now(UTC)`` when omitted.
    """
    # TODO: wire up reminder service
    current_time = now or datetime.now(timezone.utc)
    return {"time": current_time.isoformat(), "reminders_fired": []}
