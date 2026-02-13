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
