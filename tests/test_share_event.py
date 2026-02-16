"""API tests for sharing events."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.domain.models import Event, EventStatus
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


def _seed_event() -> Event:
    now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    event = Event(
        title="Shareable event",
        start_time=now + timedelta(days=1),
        end_time=now + timedelta(days=1, hours=1),
        location="Library",
        status=EventStatus.CONFIRMED,
    )
    event_repo.add(event)
    return event


def test_share_event_returns_expected_payload(client: TestClient):
    event = _seed_event()

    resp = client.post(
        f"/events/{event.id}/share",
        json={"targets": ["alice@example.com", "bob@example.com"]},
    )
    assert resp.status_code == 200
    body = resp.json()

    assert body["event_id"] == event.id
    assert body["title"] == event.title
    assert body["start_time"] == event.start_time.isoformat()
    assert body["end_time"] == event.end_time.isoformat()
    assert body["location"] == event.location
    assert body["shared_with"] == ["alice@example.com", "bob@example.com"]


def test_share_event_404_for_missing_event(client: TestClient):
    resp = client.post("/events/not-found/share", json={"targets": ["alice"]})
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Event not found"


def test_share_event_requires_targets_list(client: TestClient):
    event = _seed_event()

    missing_targets = client.post(f"/events/{event.id}/share", json={})
    assert missing_targets.status_code == 422

    wrong_type = client.post(f"/events/{event.id}/share", json={"targets": "alice"})
    assert wrong_type.status_code == 422
