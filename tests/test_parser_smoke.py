"""Smoke tests for the natural-language parser service."""

import pytest

from app.domain.models import UnstructuredEvent
from app.services.parser import parse_event


def test_parse_event_placeholder_raises():
    """The placeholder implementation raises NotImplementedError."""
    with pytest.raises(NotImplementedError):
        parse_event(UnstructuredEvent(raw_text="Dinner tomorrow at 7pm"))
