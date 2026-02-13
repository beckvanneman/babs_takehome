"""Tests for the conflict-detection service."""

import pytest

from app.domain.models import StructuredEvent
from app.services.conflicts import detect_conflicts


def test_detect_conflicts_placeholder_raises():
    """The placeholder implementation raises NotImplementedError."""
    from datetime import datetime

    event = StructuredEvent(title="Test", start=datetime(2025, 1, 1, 10, 0))
    with pytest.raises(NotImplementedError):
        detect_conflicts(event, [])
