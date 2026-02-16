"""Smoke tests for the natural-language parser service."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from app.services.parser import parse_unstructured_event


# Fixed reference time: Sunday 2025-06-01 12:00 UTC
NOW = datetime(2025, 6, 1, 12, 0, tzinfo=timezone.utc)


def _patch_llm(extracted: dict):
    """Patch _extract_with_llm to return *extracted* without calling OpenAI."""
    return patch("app.services.parser._extract_with_llm", return_value=extracted)


def test_parse_day_time_and_location():
    """Parses 'Thursday at 3:30pm at Sunset Field' into start_time and location."""
    with _patch_llm(
        {
            "title": "Event",
            "start_time": "Thursday at 3:30pm",
            "end_time": None,
            "location": "Sunset Field",
        }
    ):
        proposed, _ = parse_unstructured_event(
            "Thursday at 3:30pm at Sunset Field", NOW
        )

    # Thursday after 2025-06-01 (Sunday) is 2025-06-05
    assert proposed.start_time == datetime(2025, 6, 5, 15, 30, tzinfo=timezone.utc)
    assert proposed.location == "Sunset Field"


def test_raises_when_no_time():
    """Raises ValueError when no time is present."""
    with _patch_llm(
        {
            "title": "Team meeting",
            "start_time": None,
            "end_time": None,
            "location": None,
        }
    ):
        with pytest.raises(ValueError, match="No date/time found"):
            parse_unstructured_event("Team meeting", NOW)


def test_default_duration_60_minutes():
    """Default duration is 60 minutes when no end time is given."""
    with _patch_llm(
        {
            "title": "Lunch",
            "start_time": "tomorrow at noon",
            "end_time": None,
            "location": None,
        }
    ):
        proposed, _ = parse_unstructured_event("Lunch tomorrow at noon", NOW)

    assert proposed.end_time == proposed.start_time + timedelta(minutes=60)


def test_notes_contain_raw_text():
    """Notes field contains the original raw text."""
    with _patch_llm(
        {
            "title": "Dentist",
            "start_time": "tomorrow at 2pm",
            "end_time": None,
            "location": None,
        }
    ):
        raw = "Dentist appointment tomorrow at 2pm"
        proposed, _ = parse_unstructured_event(raw, NOW)

    assert proposed.notes == raw


# ---------------------------------------------------------------------------
# Recurrence parsing
# ---------------------------------------------------------------------------


def test_recurring_event_sets_recurrence_fields():
    """Recurring input populates recurrence_description and begin_recurrence."""
    with _patch_llm(
        {
            "title": "Soccer practice",
            "start_time": "Thursday at 3:30pm",
            "end_time": None,
            "location": "Sunset Field",
            "recurrence_description": "every Thursday",
            "recurrence_end_description": "until end of May",
        }
    ):
        proposed, ambiguities = parse_unstructured_event(
            "Soccer practice every Thursday at 3:30pm at Sunset Field until end of May",
            NOW,
        )

    assert proposed.recurrence_description == "every Thursday"
    assert proposed.begin_recurrence is not None
    assert proposed.end_recurrence_description == "until end of May"
    # No interval phrase → no begin_recurrence ambiguity
    assert not any(a.field == "begin_recurrence" for a in ambiguities)
    # End description is present → no end ambiguity
    assert not any(a.field == "end_recurrence_description" for a in ambiguities)


def test_every_other_generates_begin_recurrence_ambiguity():
    """'Every other Thursday' generates an ambiguity for begin_recurrence."""
    with _patch_llm(
        {
            "title": "Soccer practice",
            "start_time": "Thursday at 3:30pm",
            "end_time": None,
            "location": None,
            "recurrence_description": "every other Thursday",
            "recurrence_end_description": "for the 2026 season",
        }
    ):
        proposed, ambiguities = parse_unstructured_event(
            "Soccer practice every other Thursday at 3:30pm for the 2026 season",
            NOW,
        )

    begin_amb = [a for a in ambiguities if a.field == "begin_recurrence"]
    assert len(begin_amb) == 1
    assert len(begin_amb[0].options) == 2


def test_recurring_without_end_generates_ambiguity():
    """Recurring event with no end description flags end_recurrence_description."""
    with _patch_llm(
        {
            "title": "Team standup",
            "start_time": "Monday at 9am",
            "end_time": None,
            "location": None,
            "recurrence_description": "every Monday",
            "recurrence_end_description": None,
        }
    ):
        _, ambiguities = parse_unstructured_event(
            "Team standup every Monday at 9am", NOW
        )

    end_amb = [a for a in ambiguities if a.field == "end_recurrence_description"]
    assert len(end_amb) == 1


def test_non_recurring_has_no_recurrence_fields():
    """Non-recurring input leaves recurrence fields as None."""
    with _patch_llm(
        {
            "title": "Dentist",
            "start_time": "tomorrow at 2pm",
            "end_time": None,
            "location": None,
            "recurrence_description": None,
            "recurrence_end_description": None,
        }
    ):
        proposed, ambiguities = parse_unstructured_event(
            "Dentist appointment tomorrow at 2pm", NOW
        )

    assert proposed.recurrence_description is None
    assert proposed.begin_recurrence is None
    assert proposed.end_recurrence_description is None
    assert ambiguities == []
