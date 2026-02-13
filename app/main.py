"""FastAPI application — entry point for the event lifecycle service."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException

from app.domain.bus import EventBus
from app.domain.models import StructuredEvent, UnstructuredEvent
from app.repos.memory import EventRepository, ReminderRepository

app = FastAPI(title="Event Lifecycle Service")

# ── Singletons (created at import time for simplicity) ────────────────
event_bus = EventBus()
event_repo = EventRepository()
reminder_repo = ReminderRepository()


# ── Routes ────────────────────────────────────────────────────────────


@app.post("/parse", response_model=StructuredEvent)
def parse_unstructured_event(payload: UnstructuredEvent) -> StructuredEvent:
    """Accept free-text, parse it into a StructuredEvent, and persist it."""
    # TODO: wire up parser service + publish EventCreated
    raise HTTPException(status_code=501, detail="parse endpoint not yet implemented")


@app.get("/events", response_model=list[StructuredEvent])
def list_events() -> list[StructuredEvent]:
    """Return all stored events."""
    return event_repo.list_all()


@app.get("/events/{event_id}", response_model=StructuredEvent)
def get_event(event_id: str) -> StructuredEvent:
    """Return a single event by id."""
    event = event_repo.get(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


@app.post("/tick")
def tick(now: Optional[datetime] = None) -> dict:
    """Advance simulated time and fire any due reminders.

    Pass *now* as a query/body param to control the simulated clock.
    Defaults to ``datetime.utcnow()`` when omitted.
    """
    # TODO: wire up reminder service
    current_time = now or datetime.utcnow()
    return {"time": current_time.isoformat(), "reminders_fired": []}
