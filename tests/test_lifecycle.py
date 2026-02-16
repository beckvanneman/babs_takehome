"""Tests for the event bus lifecycle — handlers, reminders, conflicts."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.domain.bus import EventBus
from app.domain.events import (
    ConflictDetected,
    EventConfirmed,
    EventCreated,
    EventShared,
    ReminderSent,
)
from app.domain.handlers import HandlerRegistry
from app.domain.models import Event
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
        is_confirmed=True,
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
    assert "created" in types
    assert "reminder_scheduled" in types


# ---------------------------------------------------------------------------
# Conflict detection
# ---------------------------------------------------------------------------


def test_no_conflict_stays_confirmed(env):
    """An event with no overlaps stays is_confirmed=True."""
    event = _make_event()
    env.event_repo.add(event)

    env.bus.publish(EventCreated(event_id=event.id))

    assert event.is_confirmed is True


def test_conflict_unconfirms_and_requeues(env):
    """Overlapping events trigger ConflictDetected, un-confirm, and re-queue."""
    # existing event
    existing = _make_event(title="Existing meeting")
    env.event_repo.add(existing)

    # new event overlapping with the existing one
    new_event = _make_event(title="Conflicting meeting")
    env.event_repo.add(new_event)

    env.bus.publish(EventCreated(event_id=new_event.id))

    # Event should be un-confirmed
    assert new_event.is_confirmed is False

    # A conflict timeline entry should exist
    entries = env.timeline_repo.list_for_event(new_event.id)
    conflict_entries = [e for e in entries if e.type == "conflict_detected"]
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
    assert new_event.is_confirmed is False

    # Human reviews and re-confirms (simulate by setting confirmed and re-publishing)
    new_event.is_confirmed = True
    env.bus.publish(EventCreated(event_id=new_event.id))

    # Should stay confirmed — conflict check was skipped
    assert new_event.is_confirmed is True


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
    shared_entries = [e for e in entries if e.type == "shared"]
    assert len(shared_entries) == 1
    assert shared_entries[0].payload["targets"] == ["alice", "bob"]


# ---------------------------------------------------------------------------
# Confirmed handler
# ---------------------------------------------------------------------------


def test_confirmed_handler(env):
    """EventConfirmed sets is_confirmed and adds a timeline entry."""
    event = _make_event(is_confirmed=False)
    env.event_repo.add(event)

    env.bus.publish(EventConfirmed(event_id=event.id))

    assert event.is_confirmed is True

    entries = env.timeline_repo.list_for_event(event.id)
    confirmed_entries = [e for e in entries if e.type == "confirmed"]
    assert len(confirmed_entries) == 1
