"""Tests for the event bus lifecycle — handlers, reminders, conflicts."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.domain.bus import EventBus
from app.domain.events import (
    ConflictDetected,
    EventConfirmed,
    EventCreated,
    EventShared,
    ReminderSent,
)
from app.domain.models import ParseResponse, ProposedEvent
from app.main import (
    app,
    event_repo as app_event_repo,
    parse_response_repo as app_parse_response_repo,
    reminder_pref_repo as app_reminder_pref_repo,
    reminder_schedule_repo as app_reminder_schedule_repo,
    timeline_repo as app_timeline_repo,
)
from app.domain.handlers import HandlerRegistry
from app.domain.models import Event, EventStatus, TimelineEntryType
from app.repos.memory import (
    EventRepository,
    ParseResponseRepository,
    ReminderPreferenceRepository,
    ReminderScheduleRepository,
    TimelineRepository,
)

_NOW = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)


@pytest.fixture()
def env():
    """Fresh bus + repos + registry for each test."""
    bus = EventBus()
    event_repo = EventRepository()
    timeline_repo = TimelineRepository()
    reminder_pref_repo = ReminderPreferenceRepository()
    reminder_schedule_repo = ReminderScheduleRepository()
    parse_response_repo = ParseResponseRepository()

    registry = HandlerRegistry(
        bus=bus,
        event_repo=event_repo,
        timeline_repo=timeline_repo,
        reminder_pref_repo=reminder_pref_repo,
        reminder_schedule_repo=reminder_schedule_repo,
        parse_response_repo=parse_response_repo,
    )

    class Env:
        pass

    e = Env()
    e.bus = bus
    e.event_repo = event_repo
    e.timeline_repo = timeline_repo
    e.reminder_pref_repo = reminder_pref_repo
    e.reminder_schedule_repo = reminder_schedule_repo
    e.parse_response_repo = parse_response_repo
    e.registry = registry
    return e


def _make_event(**overrides) -> Event:
    defaults = dict(
        title="Test event",
        start_time=_NOW + timedelta(days=1),
        end_time=_NOW + timedelta(days=1, hours=1),
        status=EventStatus.CONFIRMED,
    )
    defaults.update(overrides)
    return Event(**defaults)


# ---------------------------------------------------------------------------
# Reminder scheduling
# ---------------------------------------------------------------------------


def test_event_created_schedules_reminders(env):
    """Publishing EventCreated with explicit offsets creates schedule items."""
    event = _make_event()
    env.event_repo.add(event)

    env.bus.publish(EventCreated(event_id=event.id, reminder_offsets_minutes=[60, 30]))

    items = env.reminder_schedule_repo.list_for_event(event.id)
    assert len(items) == 2

    triggers = sorted(i.trigger_time for i in items)
    assert triggers[0] == event.start_time - timedelta(minutes=60)
    assert triggers[1] == event.start_time - timedelta(minutes=30)
    assert event.reminders_scheduled is True


def test_event_created_default_offsets(env):
    """Without explicit offsets, defaults [720, 30] are used."""
    event = _make_event()
    env.event_repo.add(event)

    env.bus.publish(EventCreated(event_id=event.id))

    items = env.reminder_schedule_repo.list_for_event(event.id)
    assert len(items) == 2

    triggers = sorted(i.trigger_time for i in items)
    assert triggers[0] == event.start_time - timedelta(minutes=720)
    assert triggers[1] == event.start_time - timedelta(minutes=30)


# ---------------------------------------------------------------------------
# Timeline entries
# ---------------------------------------------------------------------------


def test_event_created_timeline(env):
    """EventCreated produces 'created' and 'reminder_scheduled' timeline entries."""
    event = _make_event()
    env.event_repo.add(event)

    env.bus.publish(EventCreated(event_id=event.id, reminder_offsets_minutes=[60]))

    entries = env.timeline_repo.list_for_event(event.id)
    types = [e.type for e in entries]
    assert TimelineEntryType.CREATED in types
    assert TimelineEntryType.REMINDER_SCHEDULED in types


# ---------------------------------------------------------------------------
# Conflict detection
# ---------------------------------------------------------------------------


def test_no_conflict_stays_confirmed(env):
    """An event with no overlaps stays confirmed."""
    event = _make_event()
    env.event_repo.add(event)

    env.bus.publish(EventCreated(event_id=event.id))

    assert event.status == EventStatus.CONFIRMED


def test_conflict_unconfirms_and_requeues(env):
    """Overlapping events trigger ConflictDetected, set conflicted status, and re-queue."""
    # existing event
    existing = _make_event(title="Existing meeting")
    env.event_repo.add(existing)

    # new event overlapping with the existing one
    new_event = _make_event(title="Conflicting meeting")
    env.event_repo.add(new_event)

    env.bus.publish(EventCreated(event_id=new_event.id))

    # Event should be conflicted
    assert new_event.status == EventStatus.CONFLICTED

    # A conflict timeline entry should exist
    entries = env.timeline_repo.list_for_event(new_event.id)
    conflict_entries = [
        e for e in entries if e.type == TimelineEntryType.CONFLICT_DETECTED
    ]
    assert len(conflict_entries) == 1
    assert existing.id in conflict_entries[0].payload["conflicting_event_ids"]

    # A new pending ParseResponse should appear for human review
    pending = env.parse_response_repo.list_pending()
    assert len(pending) == 1
    assert pending[0].proposed_event.title == "Conflicting meeting"
    assert len(pending[0].ambiguities) == 1
    assert "Conflicts with" in pending[0].ambiguities[0].reason


def test_reconfirm_after_conflict(env):
    """After conflict re-queue, re-confirming skips conflict check."""
    existing = _make_event(title="Existing meeting")
    env.event_repo.add(existing)

    new_event = _make_event(title="Conflicting meeting")
    env.event_repo.add(new_event)

    # First creation detects conflict
    env.bus.publish(EventCreated(event_id=new_event.id))
    assert new_event.status == EventStatus.CONFLICTED

    # Human reviews and re-confirms (simulate by setting confirmed and re-publishing)
    new_event.status = EventStatus.CONFIRMED
    env.bus.publish(EventCreated(event_id=new_event.id))

    # Should stay confirmed — conflict check was skipped
    assert new_event.status == EventStatus.CONFIRMED


# ---------------------------------------------------------------------------
# Reminder sent
# ---------------------------------------------------------------------------


def test_reminder_sent_updates_last_id(env):
    """Publishing ReminderSent updates last_reminder_sent_id on the event."""
    event = _make_event()
    env.event_repo.add(event)

    env.bus.publish(EventCreated(event_id=event.id, reminder_offsets_minutes=[60]))

    items = env.reminder_schedule_repo.list_for_event(event.id)
    assert len(items) == 1

    sent_at = _NOW + timedelta(hours=23)
    env.bus.publish(
        ReminderSent(
            event_id=event.id,
            schedule_item_id=items[0].id,
            sent_at=sent_at,
        )
    )

    assert event.last_reminder_sent_id == items[0].id
    assert event.reminder_last_sent_at == sent_at
    assert items[0].was_sent is True
    assert event.status == EventStatus.REMINDED


def test_two_reminders_sequential(env):
    """Fire two reminders in order; last_reminder_sent_id tracks the latest."""
    event = _make_event()
    env.event_repo.add(event)

    env.bus.publish(EventCreated(event_id=event.id, reminder_offsets_minutes=[60, 30]))

    items = env.reminder_schedule_repo.list_for_event(event.id)
    items_by_trigger = sorted(items, key=lambda i: i.trigger_time)

    # Fire the first (60 min before)
    t1 = items_by_trigger[0].trigger_time
    due_at_t1 = env.reminder_schedule_repo.list_due(t1)
    assert len(due_at_t1) == 1
    env.bus.publish(
        ReminderSent(
            event_id=event.id,
            schedule_item_id=due_at_t1[0].id,
            sent_at=t1,
        )
    )
    assert event.last_reminder_sent_id == due_at_t1[0].id

    # Fire the second (30 min before)
    t2 = items_by_trigger[1].trigger_time
    due_at_t2 = env.reminder_schedule_repo.list_due(t2)
    assert len(due_at_t2) == 1
    env.bus.publish(
        ReminderSent(
            event_id=event.id,
            schedule_item_id=due_at_t2[0].id,
            sent_at=t2,
        )
    )
    assert event.last_reminder_sent_id == due_at_t2[0].id
    assert event.last_reminder_sent_id != due_at_t1[0].id


# ---------------------------------------------------------------------------
# Shared handler
# ---------------------------------------------------------------------------


def test_shared_handler(env):
    """EventShared sets was_shared and adds a timeline entry."""
    event = _make_event()
    env.event_repo.add(event)

    env.bus.publish(EventShared(event_id=event.id, targets=["alice", "bob"]))

    assert event.was_shared is True

    entries = env.timeline_repo.list_for_event(event.id)
    shared_entries = [e for e in entries if e.type == TimelineEntryType.SHARED]
    assert len(shared_entries) == 1
    assert shared_entries[0].payload["targets"] == ["alice", "bob"]


# ---------------------------------------------------------------------------
# Confirmed handler
# ---------------------------------------------------------------------------


def test_confirmed_handler(env):
    """EventConfirmed sets status to confirmed and adds a timeline entry."""
    event = _make_event(status=EventStatus.DRAFT)
    env.event_repo.add(event)

    env.bus.publish(EventConfirmed(event_id=event.id))

    assert event.status == EventStatus.CONFIRMED

    entries = env.timeline_repo.list_for_event(event.id)
    confirmed_entries = [e for e in entries if e.type == TimelineEntryType.CONFIRMED]
    assert len(confirmed_entries) == 1


# ---------------------------------------------------------------------------
# API lifecycle coverage
# ---------------------------------------------------------------------------


@pytest.fixture()
def api_client():
    app_event_repo._store.clear()
    app_parse_response_repo._store.clear()
    app_timeline_repo._entries.clear()
    app_reminder_pref_repo._prefs.clear()
    app_reminder_schedule_repo._items.clear()

    client = TestClient(app)
    yield client

    app_event_repo._store.clear()
    app_parse_response_repo._store.clear()
    app_timeline_repo._entries.clear()
    app_reminder_pref_repo._prefs.clear()
    app_reminder_schedule_repo._items.clear()


def _seed_pending_parse_response() -> ParseResponse:
    proposed = ProposedEvent(
        title="Lifecycle appointment",
        start_time=_NOW + timedelta(days=1, hours=2),
        end_time=_NOW + timedelta(days=1, hours=3),
        location="Clinic",
        notes="Routine checkup",
    )
    pr = ParseResponse(proposed_event=proposed)
    app_parse_response_repo.add(pr)
    return pr


def test_api_event_lifecycle_confirm_share_remind(api_client: TestClient):
    """Confirm -> share -> tick should update event state and timeline."""
    pr = _seed_pending_parse_response()

    confirm_resp = api_client.post(
        f"/proposed-events/{pr.id}/confirm",
        json={"proposed_event": pr.proposed_event.model_dump(mode="json")},
    )
    assert confirm_resp.status_code == 200
    event = confirm_resp.json()
    event_id = event["id"]

    stored = app_event_repo.get(event_id)
    assert stored is not None
    assert stored.status == EventStatus.CONFIRMED
    assert stored.reminders_scheduled is True

    share_resp = api_client.post(
        f"/events/{event_id}/share",
        json={"targets": ["alice@example.com", "bob@example.com"]},
    )
    assert share_resp.status_code == 200
    assert share_resp.json()["shared_with"] == ["alice@example.com", "bob@example.com"]

    first_trigger = min(
        item.trigger_time
        for item in app_reminder_schedule_repo.list_for_event(event_id)
    )
    tick_resp = api_client.post("/tick", params={"now": first_trigger.isoformat()})
    assert tick_resp.status_code == 200
    assert len(tick_resp.json()["reminders_fired"]) == 1

    stored = app_event_repo.get(event_id)
    assert stored is not None
    assert stored.was_shared is True
    assert stored.status == EventStatus.REMINDED
    assert stored.last_reminder_sent_id is not None
    assert stored.reminder_last_sent_at == first_trigger

    timeline_resp = api_client.get(f"/events/{event_id}/timeline")
    assert timeline_resp.status_code == 200
    timeline_types = [entry["type"] for entry in timeline_resp.json()]
    assert "created" in timeline_types
    assert "reminder_scheduled" in timeline_types
    assert "shared" in timeline_types
    assert "reminder_sent" in timeline_types


def test_api_confirm_overlapping_event_becomes_conflicted(api_client: TestClient):
    """Confirming an overlapping event should mark it conflicted and re-queue review."""
    existing = _make_event(title="Existing appt")
    app_event_repo.add(existing)

    pr = ParseResponse(
        proposed_event=ProposedEvent(
            title="Overlapping appt",
            start_time=existing.start_time,
            end_time=existing.end_time,
            location="Clinic",
        )
    )
    app_parse_response_repo.add(pr)

    confirm_resp = api_client.post(
        f"/proposed-events/{pr.id}/confirm",
        json={"proposed_event": pr.proposed_event.model_dump(mode="json")},
    )
    assert confirm_resp.status_code == 200
    event_id = confirm_resp.json()["id"]

    stored = app_event_repo.get(event_id)
    assert stored is not None
    assert stored.status == EventStatus.CONFLICTED

    timeline_types = [e.type for e in app_timeline_repo.list_for_event(event_id)]
    assert TimelineEntryType.CONFLICT_DETECTED in timeline_types

    pending = app_parse_response_repo.list_pending()
    assert len(pending) == 1
    assert pending[0].event_id == event_id
