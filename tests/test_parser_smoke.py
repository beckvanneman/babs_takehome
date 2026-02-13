"""Smoke tests for the natural-language parser service."""

from datetime import datetime, timezone

import pytest

from app.services.parser import parse_unstructured_event


def test_parse_event_placeholder_raises():
    """The placeholder implementation raises NotImplementedError."""
    now = datetime(2025, 6, 1, 12, 0, tzinfo=timezone.utc)
    with pytest.raises(NotImplementedError):
        parse_unstructured_event("Dinner tomorrow at 7pm", now)
