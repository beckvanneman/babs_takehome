"""Service for creating and firing reminders."""

from __future__ import annotations

from datetime import datetime

from app.domain.models import Event, ReminderScheduleItem


def create_default_reminders(event: Event) -> list[ReminderScheduleItem]:
    """Generate default reminders for an event (e.g. 15 min before).

    Currently a placeholder.
    """
    raise NotImplementedError("create_default_reminders is not yet implemented")


def fire_due_reminders(
    reminders: list[ReminderScheduleItem],
    now: datetime,
) -> list[ReminderScheduleItem]:
    """Return reminders that should fire at the given *now* time.

    Currently a placeholder.
    """
    raise NotImplementedError("fire_due_reminders is not yet implemented")
