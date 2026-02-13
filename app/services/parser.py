"""Service for parsing unstructured text into a StructuredEvent."""

from __future__ import annotations

from app.domain.models import StructuredEvent, UnstructuredEvent


def parse_event(unstructured: UnstructuredEvent) -> StructuredEvent:
    """Parse free-text into a StructuredEvent.

    Uses ``dateparser`` to extract dates and heuristics for title/location.
    Currently a placeholder that will be fleshed out.
    """
    raise NotImplementedError("parse_event is not yet implemented")
