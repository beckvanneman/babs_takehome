"""In-memory repositories for events and reminders."""

from __future__ import annotations

from app.domain.models import Reminder, StructuredEvent


class EventRepository:
    """Dict-backed store for StructuredEvent instances, keyed by id."""

    def __init__(self) -> None:
        self._store: dict[str, StructuredEvent] = {}

    def save(self, event: StructuredEvent) -> None:
        self._store[event.id] = event

    def get(self, event_id: str) -> StructuredEvent | None:
        return self._store.get(event_id)

    def list_all(self) -> list[StructuredEvent]:
        return list(self._store.values())


class ReminderRepository:
    """List-backed store for Reminder instances."""

    def __init__(self) -> None:
        self._store: list[Reminder] = []

    def save(self, reminder: Reminder) -> None:
        self._store.append(reminder)

    def list_pending(self) -> list[Reminder]:
        return [r for r in self._store if not r.fired]

    def list_all(self) -> list[Reminder]:
        return list(self._store)
