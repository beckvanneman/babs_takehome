"""In-memory repositories for events and reminders."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.domain.models import (
    Event,
    ParseResponse,
    ReminderPreference,
    ReminderScheduleItem,
    TimelineEntry,
)


class EventRepository:
    """Dict-backed store for Event instances, keyed by id."""

    def __init__(self) -> None:
        self._store: dict[str, Event] = {}

    def add(self, event: Event) -> None:
        self._store[event.id] = event

    def get(self, event_id: str) -> Event | None:
        return self._store.get(event_id)

    def list_all(self) -> list[Event]:
        return list(self._store.values())

    def list_children(self, parent_id: str) -> list[Event]:
        """Return all child events belonging to a recurring series."""
        return [e for e in self._store.values() if e.parent_event_id == parent_id]

    def delete(self, event_id: str) -> None:
        self._store.pop(event_id, None)

    def delete_series(self, parent_id: str) -> None:
        """Delete a parent event and all its children (cascade)."""
        to_remove = [
            eid
            for eid, e in self._store.items()
            if eid == parent_id or e.parent_event_id == parent_id
        ]
        for eid in to_remove:
            del self._store[eid]


class ParseResponseRepository:
    """Dict-backed store for ParseResponse instances, keyed by id."""

    def __init__(self) -> None:
        self._store: dict[str, ParseResponse] = {}

    def add(self, parse_response: ParseResponse) -> None:
        self._store[parse_response.id] = parse_response

    def get(self, parse_response_id: str) -> ParseResponse | None:
        return self._store.get(parse_response_id)

    def list_pending(self) -> list[ParseResponse]:
        return [pr for pr in self._store.values() if pr.status == "pending"]

    def update_status(self, parse_response_id: str, status: str) -> None:
        pr = self._store.get(parse_response_id)
        if pr is not None:
            pr.status = status


class TimelineRepository:
    """List-backed store for TimelineEntry instances."""

    def __init__(self) -> None:
        self._entries: list[TimelineEntry] = []

    def add(self, entry: TimelineEntry) -> None:
        self._entries.append(entry)

    def list_for_event(self, event_id: str) -> list[TimelineEntry]:
        return sorted(
            [e for e in self._entries if e.event_id == event_id],
            key=lambda e: e.timestamp,
        )


class ReminderPreferenceRepository:
    """List-backed store for ReminderPreference instances."""

    def __init__(self) -> None:
        self._prefs: list[ReminderPreference] = []

    def add(self, pref: ReminderPreference) -> None:
        self._prefs.append(pref)

    def list_for_event(self, event_id: str) -> list[ReminderPreference]:
        return [p for p in self._prefs if p.event_id == event_id]


class ReminderScheduleRepository:
    """List-backed store for ReminderScheduleItem instances."""

    def __init__(self) -> None:
        self._items: list[ReminderScheduleItem] = []

    def add(self, item: ReminderScheduleItem) -> None:
        self._items.append(item)

    def list_due(self, now: datetime) -> list[ReminderScheduleItem]:
        return [i for i in self._items if not i.was_sent and i.trigger_time <= now]

    def mark_sent(self, item_id: str, sent_at: datetime) -> None:
        for item in self._items:
            if item.id == item_id:
                item.was_sent = True
                item.sent_at = sent_at
                return

    def list_for_event(self, event_id: str) -> list[ReminderScheduleItem]:
        return [i for i in self._items if i.event_id == event_id]


# ---------------------------------------------------------------------------
# Seed data – a few near-future events useful for conflict testing
# ---------------------------------------------------------------------------


def _seed_events(repo: EventRepository) -> None:
    now = datetime.now(timezone.utc)

    # Recurring series: Soccer practice every week for 3 weeks
    soccer_practice = Event(
        title="Soccer practice",
        start_time=now + timedelta(hours=2),
        end_time=now + timedelta(hours=3),
        location="City Park Field 4",
        is_confirmed=True,
        recurrence_rule="FREQ=WEEKLY;BYDAY=TH",
        recurrence_end=now + timedelta(weeks=3),
    )
    repo.add(soccer_practice)
    # Child occurrences
    for week in (1, 2, 3):
        repo.add(
            Event(
                title="Soccer practice",
                start_time=now + timedelta(hours=2, weeks=week),
                end_time=now + timedelta(hours=3, weeks=week),
                location="City Park Field 4",
                is_confirmed=True,
                parent_event_id=soccer_practice.id,
            )
        )

    repo.add(
        Event(
            title="Piano lesson",
            start_time=now + timedelta(hours=4),
            end_time=now + timedelta(hours=5),
            location="Music Academy",
            is_confirmed=True,
        )
    )
    repo.add(
        Event(
            title="Dentist appointment",
            start_time=now + timedelta(days=1, hours=1),
            end_time=now + timedelta(days=1, hours=2),
            location="Downtown Dental",
            is_confirmed=False,
        )
    )


def create_event_repository() -> EventRepository:
    """Return an EventRepository pre-loaded with sample data."""
    repo = EventRepository()
    _seed_events(repo)
    return repo
