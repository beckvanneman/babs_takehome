"""Service for parsing unstructured text into a ProposedEvent."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

import dateparser
from openai import OpenAI

from app.domain.models import Ambiguity, ProposedEvent

_SYSTEM_PROMPT = """\
You are an event-extraction assistant. Given a short piece of natural language \
describing a calendar event, extract the following fields as JSON:

{
  "title": "<concise event title, without time or location details>",
  "start_time": "<raw time substring from the text, or null if none>",
  "end_time": "<raw end-time substring from the text, or null if none>",
  "location": "<location name from the text, or null if none>"
}

Rules:
- For title, extract ONLY what the event is about (e.g. "Soccer practice", \
"Dinner", "Team meeting"). Strip time and location phrases.
- For start_time and end_time, extract the EXACT substring from the input \
that describes the time. Do NOT interpret or reformat it.
- For location, extract the place name if one is mentioned.
- Return null for any field that is not present in the text.
- Respond with ONLY the JSON object, no other text.
"""


def _extract_with_llm(text: str) -> dict:
    """Call OpenAI to extract structured fields from free text."""
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
        temperature=0,
        response_format={"type": "json_object"},
    )
    return json.loads(response.choices[0].message.content)


def _parse_time(raw: str | None, now: datetime) -> datetime | None:
    """Parse a raw time string using dateparser, returning a UTC datetime."""
    if not raw:
        return None
    settings = {
        "PREFER_DATES_FROM": "future",
        "RELATIVE_BASE": now.replace(tzinfo=None),
        "RETURN_AS_TIMEZONE_AWARE": False,
    }
    result = dateparser.parse(raw, settings=settings)
    if result is None:
        return None
    return result.replace(tzinfo=timezone.utc)


def parse_unstructured_event(
    text: str, now: datetime
) -> tuple[ProposedEvent, list[Ambiguity]]:
    """Parse free-text into a ProposedEvent with any detected ambiguities.

    Uses OpenAI to extract structured fields, then validates times with
    ``dateparser``.  Raises ``ValueError`` if no date/time can be found.
    """
    extracted = _extract_with_llm(text)
    ambiguities: list[Ambiguity] = []

    # -- start_time --------------------------------------------------------
    start_time = _parse_time(extracted.get("start_time"), now)
    if start_time is None:
        raise ValueError("No date/time found in text")

    # -- end_time ----------------------------------------------------------
    end_time = _parse_time(extracted.get("end_time"), now)
    if end_time is None or end_time <= start_time:
        end_time = start_time + timedelta(minutes=60)

    # -- title / location / notes ------------------------------------------
    title = extracted.get("title") or text
    location = extracted.get("location") or None

    proposed = ProposedEvent(
        title=title,
        start_time=start_time,
        end_time=end_time,
        location=location,
        notes=text,
    )
    return proposed, ambiguities
