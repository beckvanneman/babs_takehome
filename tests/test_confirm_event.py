"""End-to-end tests for the proposed-event confirmation/rejection flow."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.domain.models import Ambiguity, ParseResponse, ProposedEvent
from app.main import (
    app,
    event_repo,
    parse_response_repo,
    reminder_pref_repo,
    reminder_schedule_repo,
    timeline_repo,
)


@pytest.fixture(autouse=True)
def _clear_repos():
    """Reset in-memory repos before each test."""
    event_repo._store.clear()
    parse_response_repo._store.clear()
    timeline_repo._entries.clear()
    reminder_pref_repo._prefs.clear()
    reminder_schedule_repo._items.clear()
    yield
    event_repo._store.clear()
    parse_response_repo._store.clear()
    timeline_repo._entries.clear()
    reminder_pref_repo._prefs.clear()
    reminder_schedule_repo._items.clear()


@pytest.fixture()
def client():
    return TestClient(app)


# ---------------------------------------------------------------------------
# Stub data helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)


def _one_off_proposed() -> ProposedEvent:
    """Doctor's appointment — no recurrence, no ambiguities."""
    return ProposedEvent(
        title="Doctor's appointment",
        start_time=_NOW + timedelta(days=1, hours=2),
        end_time=_NOW + timedelta(days=1, hours=3),
        location="Downtown Clinic",
        notes="Doctor's appointment Friday at 2pm at Downtown Clinic",
    )


def _recurring_proposed() -> ProposedEvent:
    """Soccer practice every Thursday — has recurrence, fully resolved."""
    return ProposedEvent(
        title="Soccer practice",
        start_time=datetime(2026, 3, 5, 15, 30, tzinfo=timezone.utc),
        end_time=datetime(2026, 3, 5, 17, 0, tzinfo=timezone.utc),
        location="Sunset Field",
        recurrence_description="every Thursday",
        begin_recurrence=datetime(2026, 3, 5, 15, 30, tzinfo=timezone.utc),
        end_recurrence_description="until end of May",
    )


def _ambiguous_proposed() -> tuple[ProposedEvent, list[Ambiguity]]:
    """Soccer every other Thursday — ambiguity on begin_recurrence."""
    proposed = ProposedEvent(
        title="Soccer practice",
        start_time=datetime(2026, 3, 5, 15, 30, tzinfo=timezone.utc),
        end_time=datetime(2026, 3, 5, 17, 0, tzinfo=timezone.utc),
        location="Sunset Field",
        recurrence_description="every other Thursday",
        begin_recurrence=datetime(2026, 3, 5, 15, 30, tzinfo=timezone.utc),
    )
    ambiguities = [
        Ambiguity(
            field="begin_recurrence",
            reason="'every other' is ambiguous — does the series start this week or next?",
            options=["2026-03-05", "2026-03-12"],
        ),
        Ambiguity(
            field="end_recurrence_description",
            reason="No end date specified for recurring event",
            options=[],
        ),
    ]
    return proposed, ambiguities


def _seed_parse_response(
    proposed: ProposedEvent, ambiguities: list[Ambiguity] | None = None
) -> ParseResponse:
    """Create a ParseResponse, store it in the repo, and return it."""
    pr = ParseResponse(
        proposed_event=proposed,
        ambiguities=ambiguities or [],
    )
    parse_response_repo.add(pr)
    return pr


# ---------------------------------------------------------------------------
# Tests: Proposed events queue
# ---------------------------------------------------------------------------


def test_parse_appears_in_proposed_events_queue(client: TestClient):
    """A stored ParseResponse should appear in GET /proposed-events."""
    pr = _seed_parse_response(_one_off_proposed())

    resp = client.get("/proposed-events")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    assert items[0]["id"] == pr.id
    assert items[0]["status"] == "pending"


def test_proposed_events_queue_only_returns_pending(client: TestClient):
    """Confirmed/rejected items should not appear in the pending queue."""
    pr1 = _seed_parse_response(_one_off_proposed())
    pr2 = _seed_parse_response(_one_off_proposed())

    # confirm one, reject the other
    parse_response_repo.update_status(pr1.id, "confirmed")
    parse_response_repo.update_status(pr2.id, "rejected")

    resp = client.get("/proposed-events")
    assert resp.status_code == 200
    assert resp.json() == []


# ---------------------------------------------------------------------------
# Tests: Confirm one-off event
# ---------------------------------------------------------------------------


def test_confirm_one_off_creates_event(client: TestClient):
    """Confirming a one-off ProposedEvent should create an Event with no RRULE."""
    pr = _seed_parse_response(_one_off_proposed())
    proposed = _one_off_proposed()

    resp = client.post(
        f"/proposed-events/{pr.id}/confirm",
        json={"proposed_event": proposed.model_dump(mode="json")},
    )
    assert resp.status_code == 200
    event = resp.json()

    assert event["title"] == "Doctor's appointment"
    assert event["location"] == "Downtown Clinic"
    assert event["is_confirmed"] is True
    assert event["recurrence_rule"] is None
    assert event["proposed_event_id"] == pr.id


def test_confirm_one_off_appears_in_events(client: TestClient):
    """After confirmation, the event should be retrievable via GET /events."""
    pr = _seed_parse_response(_one_off_proposed())
    proposed = _one_off_proposed()

    client.post(
        f"/proposed-events/{pr.id}/confirm",
        json={"proposed_event": proposed.model_dump(mode="json")},
    )

    resp = client.get("/events")
    assert resp.status_code == 200
    events = resp.json()
    assert len(events) == 1
    assert events[0]["title"] == "Doctor's appointment"


def test_confirm_one_off_removes_from_pending(client: TestClient):
    """After confirmation, the proposed event should no longer be pending."""
    pr = _seed_parse_response(_one_off_proposed())
    proposed = _one_off_proposed()

    client.post(
        f"/proposed-events/{pr.id}/confirm",
        json={"proposed_event": proposed.model_dump(mode="json")},
    )

    resp = client.get("/proposed-events")
    assert resp.json() == []


# ---------------------------------------------------------------------------
# Tests: Confirm recurring event
# ---------------------------------------------------------------------------


def test_confirm_recurring_creates_event_with_rrule(client: TestClient):
    """A recurring ProposedEvent should produce an Event with an RRULE."""
    pr = _seed_parse_response(_recurring_proposed())
    proposed = _recurring_proposed()

    resp = client.post(
        f"/proposed-events/{pr.id}/confirm",
        json={"proposed_event": proposed.model_dump(mode="json")},
    )
    assert resp.status_code == 200
    event = resp.json()

    assert event["recurrence_rule"] is not None
    assert "FREQ=WEEKLY" in event["recurrence_rule"]
    assert "BYDAY=TH" in event["recurrence_rule"]
    assert event["proposed_event_id"] == pr.id


# ---------------------------------------------------------------------------
# Tests: Confirm with resolved ambiguities
# ---------------------------------------------------------------------------


def test_confirm_with_resolved_ambiguities(client: TestClient):
    """Client resolves ambiguities before confirming — resolved values are used."""
    proposed, ambiguities = _ambiguous_proposed()
    pr = _seed_parse_response(proposed, ambiguities)

    # Client resolves: pick the later start date and add an end date
    resolved = proposed.model_copy(
        update={
            "begin_recurrence": datetime(2026, 3, 12, 15, 30, tzinfo=timezone.utc),
            "end_recurrence_description": "until end of April",
        }
    )

    resp = client.post(
        f"/proposed-events/{pr.id}/confirm",
        json={"proposed_event": resolved.model_dump(mode="json")},
    )
    assert resp.status_code == 200
    event = resp.json()

    assert event["recurrence_rule"] is not None
    assert "INTERVAL=2" in event["recurrence_rule"]
    assert event["is_confirmed"] is True


# ---------------------------------------------------------------------------
# Tests: Reject
# ---------------------------------------------------------------------------


def test_reject_proposed_event(client: TestClient):
    """Rejecting a proposed event should mark it rejected, create no Event."""
    pr = _seed_parse_response(_one_off_proposed())

    resp = client.post(f"/proposed-events/{pr.id}/reject")
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"

    # No event created
    events_resp = client.get("/events")
    assert events_resp.json() == []

    # No longer in pending queue
    pending_resp = client.get("/proposed-events")
    assert pending_resp.json() == []


def test_reject_then_confirm_fails(client: TestClient):
    """Cannot confirm an already-rejected proposed event."""
    pr = _seed_parse_response(_one_off_proposed())
    proposed = _one_off_proposed()

    client.post(f"/proposed-events/{pr.id}/reject")

    resp = client.post(
        f"/proposed-events/{pr.id}/confirm",
        json={"proposed_event": proposed.model_dump(mode="json")},
    )
    assert resp.status_code == 400
    assert "rejected" in resp.json()["detail"]


def test_confirm_then_reject_fails(client: TestClient):
    """Cannot reject an already-confirmed proposed event."""
    pr = _seed_parse_response(_one_off_proposed())
    proposed = _one_off_proposed()

    client.post(
        f"/proposed-events/{pr.id}/confirm",
        json={"proposed_event": proposed.model_dump(mode="json")},
    )

    resp = client.post(f"/proposed-events/{pr.id}/reject")
    assert resp.status_code == 400
    assert "confirmed" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Tests: Error cases
# ---------------------------------------------------------------------------


def test_confirm_nonexistent_returns_404(client: TestClient):
    resp = client.post(
        "/proposed-events/bogus-id/confirm",
        json={"proposed_event": _one_off_proposed().model_dump(mode="json")},
    )
    assert resp.status_code == 404


def test_reject_nonexistent_returns_404(client: TestClient):
    resp = client.post("/proposed-events/bogus-id/reject")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Tests: Event links back to ProposedEvent
# ---------------------------------------------------------------------------


def test_event_links_to_proposed_event(client: TestClient):
    """The created Event should carry the proposed_event_id of its origin."""
    pr = _seed_parse_response(_one_off_proposed())
    proposed = _one_off_proposed()

    resp = client.post(
        f"/proposed-events/{pr.id}/confirm",
        json={"proposed_event": proposed.model_dump(mode="json")},
    )
    event = resp.json()
    assert event["proposed_event_id"] == pr.id

    # Also verify via GET /events/{id}
    event_resp = client.get(f"/events/{event['id']}")
    assert event_resp.status_code == 200
    assert event_resp.json()["proposed_event_id"] == pr.id
