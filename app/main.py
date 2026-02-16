"""FastAPI application — entry point for the event lifecycle service."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException

from app.domain.bus import EventBus
from app.domain.models import ConfirmEventRequest, Event, ParseRequest, ParseResponse
from app.repos.memory import EventRepository, ParseResponseRepository, ReminderScheduleRepository
from app.services.parser import parse_unstructured_event as _parse
from app.services.recurrence import compile_rrule

app = FastAPI(title="Event Lifecycle Service")

# ── Singletons (created at import time for simplicity) ────────────────
event_bus = EventBus()
event_repo = EventRepository()
parse_response_repo = ParseResponseRepository()
reminder_repo = ReminderScheduleRepository()


# ── Routes ────────────────────────────────────────────────────────────


@app.post("/parse", response_model=ParseResponse)
def parse_event(payload: ParseRequest) -> ParseResponse:
    """Accept free-text and return a proposed event with any ambiguities."""
    now = datetime.now(timezone.utc)
    proposed_event, ambiguities = _parse(payload.text, now)
    parse_response = ParseResponse(proposed_event=proposed_event, ambiguities=ambiguities)
    parse_response_repo.add(parse_response)
    return parse_response


@app.get("/proposed-events", response_model=list[ParseResponse])
def list_proposed_events() -> list[ParseResponse]:
    """Return all pending proposed events."""
    return parse_response_repo.list_pending()


@app.post("/proposed-events/{proposed_event_id}/confirm", response_model=Event)
def confirm_proposed_event(
    proposed_event_id: str, body: ConfirmEventRequest
) -> Event:
    """Confirm a proposed event and create a stored Event."""
    pr = parse_response_repo.get(proposed_event_id)
    if pr is None:
        raise HTTPException(status_code=404, detail="Proposed event not found")
    if pr.status != "pending":
        raise HTTPException(
            status_code=400,
            detail=f"Proposed event is already {pr.status}",
        )

    proposed = body.proposed_event
    recurrence_rule = compile_rrule(proposed)
    event = Event(
        title=proposed.title,
        start_time=proposed.start_time,
        end_time=proposed.end_time,
        location=proposed.location,
        notes=proposed.notes,
        is_confirmed=True,
        proposed_event_id=pr.id,
        recurrence_rule=recurrence_rule,
        recurrence_end=proposed.begin_recurrence if recurrence_rule else None,
    )
    event_repo.add(event)
    parse_response_repo.update_status(proposed_event_id, "confirmed")
    return event


@app.post("/proposed-events/{proposed_event_id}/reject", status_code=200)
def reject_proposed_event(proposed_event_id: str) -> dict:
    """Reject a proposed event."""
    pr = parse_response_repo.get(proposed_event_id)
    if pr is None:
        raise HTTPException(status_code=404, detail="Proposed event not found")
    if pr.status != "pending":
        raise HTTPException(
            status_code=400,
            detail=f"Proposed event is already {pr.status}",
        )
    parse_response_repo.update_status(proposed_event_id, "rejected")
    return {"status": "rejected"}


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
def tick(now: datetime | None = None) -> dict:
    """Advance simulated time and fire any due reminders.

    Pass *now* as a query/body param to control the simulated clock.
    Defaults to ``datetime.now(timezone.utc)`` when omitted.
    """
    # TODO: wire up reminder service
    current_time = now or datetime.now(timezone.utc)
    return {"time": current_time.isoformat(), "reminders_fired": []}
