"""Service for creating and firing reminders."""

from __future__ import annotations

from datetime import datetime

from app.domain.models import Reminder, StructuredEvent


def create_default_reminders(event: StructuredEvent) -> list[Reminder]:
    """Generate default reminders for an event (e.g. 15 min before).

    Currently a placeholder.
    """
    raise NotImplementedError("create_default_reminders is not yet implemented")


def fire_due_reminders(
    reminders: list[Reminder],
    now: datetime,
) -> list[Reminder]:
    """Return reminders that should fire at the given *now* time.

    Currently a placeholder.
    """
    raise NotImplementedError("fire_due_reminders is not yet implemented")
