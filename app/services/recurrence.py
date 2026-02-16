"""Service for compiling human-readable recurrence into RRULE strings and
expanding recurring events into individual child occurrences."""

from __future__ import annotations

import re
from datetime import datetime, timezone

from dateutil.rrule import (
    DAILY,
    MONTHLY,
    WEEKLY,
    FR,
    MO,
    SA,
    SU,
    TH,
    TU,
    WE,
    rrule,
    rrulestr,
)

from app.domain.models import Event, ProposedEvent

_DAY_MAP = {
    "monday": MO,
    "tuesday": TU,
    "wednesday": WE,
    "thursday": TH,
    "friday": FR,
    "saturday": SA,
    "sunday": SU,
}


def compile_rrule(proposed: ProposedEvent) -> str | None:
    """Compile a ProposedEvent's human-readable recurrence fields into an RRULE string.

    Returns ``None`` if the proposed event has no recurrence.
    """
    if not proposed.recurrence_description:
        return None

    desc = proposed.recurrence_description.lower().strip()

    # Determine frequency and interval
    freq = WEEKLY  # default for day-of-week patterns
    interval = 1

    if any(phrase in desc for phrase in ("every other", "biweekly", "bi-weekly")):
        interval = 2
    else:
        # Check for "every N weeks/days" pattern
        m = re.search(r"every\s+(\d+)\s+(week|day|month)", desc)
        if m:
            interval = int(m.group(1))
            unit = m.group(2)
            if unit == "day":
                freq = DAILY
            elif unit == "month":
                freq = MONTHLY

    if "daily" in desc or "every day" in desc:
        freq = DAILY
    elif "monthly" in desc or "every month" in desc:
        freq = MONTHLY

    # Determine day(s) of week
    by_day = []
    for day_name, day_const in _DAY_MAP.items():
        if day_name in desc:
            by_day.append(day_const)

    # Also check for "weekday(s)"
    if "weekday" in desc:
        by_day = [MO, TU, WE, TH, FR]

    # Build RRULE parts
    parts = [f"FREQ={_freq_name(freq)}"]
    if interval > 1:
        parts.append(f"INTERVAL={interval}")
    if by_day and freq == WEEKLY:
        parts.append("BYDAY=" + ",".join(_day_abbr(d) for d in by_day))

    return ";".join(parts)


def expand_recurrence(parent: Event) -> list[Event]:
    """Expand a parent Event's recurrence rule into child Event instances.

    The parent's own date is excluded from the result (it is already an event).
    Each child copies the parent's title, location, notes, and duration, with
    ``parent_id`` set to the parent's id and ``recurrence_rule`` left as None.
    """
    if not parent.recurrence_rule or not parent.recurrence_end:
        return []

    duration = parent.end_time - parent.start_time

    # Build an rrule starting from the parent's start_time
    rule_str = (
        f"DTSTART:{parent.start_time.strftime('%Y%m%dT%H%M%SZ')}\n"
        f"RRULE:{parent.recurrence_rule}"
        f";UNTIL={parent.recurrence_end.strftime('%Y%m%dT%H%M%SZ')}"
    )
    rule = rrulestr(rule_str)

    children: list[Event] = []
    for dt in rule:
        # Make sure the datetime is timezone-aware
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        # Skip the parent's own occurrence
        if dt == parent.start_time:
            continue
        children.append(
            Event(
                title=parent.title,
                start_time=dt,
                end_time=dt + duration,
                location=parent.location,
                notes=parent.notes,
                parent_id=parent.id,
                is_confirmed=parent.is_confirmed,
            )
        )

    return children


def _freq_name(freq: int) -> str:
    return {DAILY: "DAILY", WEEKLY: "WEEKLY", MONTHLY: "MONTHLY"}[freq]


def _day_abbr(day_const) -> str:
    return {MO: "MO", TU: "TU", WE: "WE", TH: "TH", FR: "FR", SA: "SA", SU: "SU"}[
        day_const
    ]
