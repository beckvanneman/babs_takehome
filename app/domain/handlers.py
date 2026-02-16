"""Domain event handlers — wired up at application startup."""

from __future__ import annotations

from datetime import timedelta

from app.domain.bus import EventBus
from app.domain.events import (
    ConflictDetected,
    EventConfirmed,
    EventCreated,
    EventShared,
    ReminderSent,
)
from app.domain.models import (
    Ambiguity,
    ParseResponse,
    ProposedEvent,
    ReminderPreference,
    ReminderScheduleItem,
    TimelineEntry,
)
from app.repos.memory import (
    EventRepository,
    ParseResponseRepository,
    ReminderPreferenceRepository,
    ReminderScheduleRepository,
    TimelineRepository,
)
from app.services.conflicts import find_conflicts

_DEFAULT_OFFSETS = [720, 30]  # 12 hours, 30 minutes


class HandlerRegistry:
    """Wires domain-event handlers to the bus with access to all repositories."""

    def __init__(
        self,
        bus: EventBus,
        event_repo: EventRepository,
        timeline_repo: TimelineRepository,
        reminder_pref_repo: ReminderPreferenceRepository,
        reminder_schedule_repo: ReminderScheduleRepository,
        parse_response_repo: ParseResponseRepository,
    ) -> None:
        self.bus = bus
        self.event_repo = event_repo
        self.timeline_repo = timeline_repo
        self.reminder_pref_repo = reminder_pref_repo
        self.reminder_schedule_repo = reminder_schedule_repo
        self.parse_response_repo = parse_response_repo
        self._register()

    def _register(self) -> None:
        self.bus.subscribe(EventCreated, self.on_event_created)
        self.bus.subscribe(ConflictDetected, self.on_conflict_detected)
        self.bus.subscribe(EventShared, self.on_event_shared)
        self.bus.subscribe(EventConfirmed, self.on_event_confirmed)
        self.bus.subscribe(ReminderSent, self.on_reminder_sent)

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def on_event_created(self, event: EventCreated) -> None:
        stored = self.event_repo.get(event.event_id)
        if stored is None:
            return

        # 1. Timeline: created
        self.timeline_repo.add(TimelineEntry(event_id=event.event_id, type="created"))

        # 2. Schedule reminders
        offsets = event.reminder_offsets_minutes or _DEFAULT_OFFSETS
        schedule_ids: list[str] = []
        for offset in offsets:
            pref = ReminderPreference(
                event_id=event.event_id,
                offset_minutes=offset,
            )
            self.reminder_pref_repo.add(pref)

            item = ReminderScheduleItem(
                event_id=event.event_id,
                preference_id=pref.id,
                trigger_time=stored.start_time - timedelta(minutes=offset),
                channel=pref.channel,
                target=pref.target,
            )
            self.reminder_schedule_repo.add(item)
            schedule_ids.append(item.id)

        # 3. Mark reminders as scheduled
        stored.reminders_scheduled = True

        # 4. Timeline: reminder_scheduled
        self.timeline_repo.add(
            TimelineEntry(
                event_id=event.event_id,
                type="reminder_scheduled",
                payload={"offsets": offsets, "schedule_item_ids": schedule_ids},
            )
        )

        # 5. Check conflicts (skip if this event was already flagged for conflicts —
        #    avoids infinite re-queue loop on re-confirm)
        existing_timeline = self.timeline_repo.list_for_event(event.event_id)
        already_had_conflict = any(
            e.type == "conflict_detected" for e in existing_timeline
        )

        if not already_had_conflict:
            others = [e for e in self.event_repo.list_all() if e.id != event.event_id]
            conflicts = find_conflicts(stored.start_time, stored.end_time, others)
            if conflicts:
                self.bus.publish(
                    ConflictDetected(
                        event_id=event.event_id,
                        conflicting_event_ids=[c.id for c in conflicts],
                    )
                )

    def on_conflict_detected(self, event: ConflictDetected) -> None:
        stored = self.event_repo.get(event.event_id)
        if stored is None:
            return

        # 1. Timeline
        self.timeline_repo.add(
            TimelineEntry(
                event_id=event.event_id,
                type="conflict_detected",
                payload={"conflicting_event_ids": event.conflicting_event_ids},
            )
        )

        # 2. Un-confirm
        stored.is_confirmed = False

        # 3. Build conflict descriptions
        conflict_titles = []
        for cid in event.conflicting_event_ids:
            conflicting = self.event_repo.get(cid)
            if conflicting:
                conflict_titles.append(f"{conflicting.title} ({cid})")
            else:
                conflict_titles.append(cid)

        # 4. Re-queue as a pending proposed event with conflict ambiguity
        proposed = ProposedEvent(
            title=stored.title,
            start_time=stored.start_time,
            end_time=stored.end_time,
            location=stored.location,
            notes=stored.notes,
        )
        pr = ParseResponse(
            proposed_event=proposed,
            ambiguities=[
                Ambiguity(
                    field="time",
                    reason=f"Conflicts with: {', '.join(conflict_titles)}",
                    options=["Keep both", "Cancel this event"],
                )
            ],
        )
        self.parse_response_repo.add(pr)

    def on_event_shared(self, event: EventShared) -> None:
        stored = self.event_repo.get(event.event_id)
        if stored is None:
            return

        stored.was_shared = True
        self.timeline_repo.add(
            TimelineEntry(
                event_id=event.event_id,
                type="shared",
                payload={"targets": event.targets},
            )
        )

    def on_event_confirmed(self, event: EventConfirmed) -> None:
        stored = self.event_repo.get(event.event_id)
        if stored is None:
            return

        stored.is_confirmed = True
        self.timeline_repo.add(TimelineEntry(event_id=event.event_id, type="confirmed"))

    def on_reminder_sent(self, event: ReminderSent) -> None:
        stored = self.event_repo.get(event.event_id)
        if stored is None:
            return

        # 1. Mark schedule item as sent
        self.reminder_schedule_repo.mark_sent(event.schedule_item_id, event.sent_at)

        # 2. Update event tracking fields
        stored.last_reminder_sent_id = event.schedule_item_id
        stored.reminder_last_sent_at = event.sent_at

        # 3. Timeline
        self.timeline_repo.add(
            TimelineEntry(
                event_id=event.event_id,
                type="reminder_sent",
                payload={"schedule_item_id": event.schedule_item_id},
            )
        )
