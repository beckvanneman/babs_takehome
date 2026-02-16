"""Service for creating and firing reminders."""

from __future__ import annotations

from datetime import datetime, timedelta

from app.domain.models import ReminderPreference, ReminderScheduleItem
from app.repos.memory import ReminderPreferenceRepository, ReminderScheduleRepository

DEFAULT_OFFSETS = [720, 30]  # 12 hours, 30 minutes


def schedule_reminders(
    event_id: str,
    start_time: datetime,
    offsets_minutes: list[int],
    pref_repo: ReminderPreferenceRepository,
    schedule_repo: ReminderScheduleRepository,
) -> list[ReminderScheduleItem]:
    """Create reminder preferences and schedule items for the given offsets.

    Returns the list of created ReminderScheduleItem instances.
    """
    items: list[ReminderScheduleItem] = []
    for offset in offsets_minutes:
        pref = ReminderPreference(event_id=event_id, offset_minutes=offset)
        pref_repo.add(pref)

        item = ReminderScheduleItem(
            event_id=event_id,
            preference_id=pref.id,
            trigger_time=start_time - timedelta(minutes=offset),
            channel=pref.channel,
            target=pref.target,
        )
        schedule_repo.add(item)
        items.append(item)

    return items
