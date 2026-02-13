"""Service for parsing unstructured text into a ProposedEvent."""

from __future__ import annotations

from datetime import datetime

from app.domain.models import Ambiguity, ProposedEvent


def parse_unstructured_event(
    text: str, now: datetime
) -> tuple[ProposedEvent, list[Ambiguity]]:
    """Parse free-text into a ProposedEvent with any detected ambiguities.

    Uses ``now`` as a reference point for resolving relative dates
    (e.g. "tomorrow", "next Friday").

    Currently a placeholder that will be fleshed out.
    """
    raise NotImplementedError("parse_unstructured_event is not yet implemented")
