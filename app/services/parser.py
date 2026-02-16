"""Service for parsing unstructured text into a ProposedEvent."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

import dateparser

from app.domain.models import Ambiguity, ProposedEvent

_SYSTEM_PROMPT = """\
You are an event-extraction assistant. Given a short piece of natural language \
describing a calendar event, extract the following fields as JSON:

{
  "title": "<concise event title, without time or location details>",
  "start_time": "<raw time substring from the text, or null if none>",
  "end_time": "<raw end-time substring from the text, or null if none>",
  "location": "<location name from the text, or null if none>",
  "recurrence_description": "<raw recurrence substring, or null if not recurring>",
  "recurrence_end_description": "<raw end-of-recurrence substring, or null if none>"
}

Rules:
- For title, extract ONLY what the event is about (e.g. "Soccer practice", \
"Dinner", "Team meeting"). Strip time, location, and recurrence phrases.
- For start_time and end_time, extract the EXACT substring from the input \
that describes the time. Do NOT interpret or reformat it.
- For location, extract the place name if one is mentioned.
- For recurrence_description, extract the EXACT substring that describes how \
often the event repeats (e.g. "every Thursday", "every other week", "weekly"). \
Return null if this is a one-time event.
- For recurrence_end_description, extract the EXACT substring that describes \
when the recurrence ends (e.g. "until June", "for the 2026 season", \
"through the end of May"). Return null if no end is mentioned.
- Return null for any field that is not present in the text.
- Respond with ONLY the JSON object, no other text.
"""


def _extract_with_llm(text: str) -> dict:
    """Call OpenAI to extract structured fields from free text."""
    from openai import OpenAI

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

    # -- recurrence --------------------------------------------------------
    recurrence_description = extracted.get("recurrence_description") or None
    end_recurrence_description = extracted.get("recurrence_end_description") or None
    begin_recurrence: datetime | None = None

    if recurrence_description:
        # Use the parsed start_time as the anchor for the first occurrence.
        begin_recurrence = start_time

        # If the description implies an interval (e.g. "every other"), the
        # anchor date is ambiguous — it could be this week or next.
        desc_lower = recurrence_description.lower()
        has_interval = any(
            phrase in desc_lower
            for phrase in ("every other", "biweekly", "bi-weekly", "every 2")
        )
        if has_interval:
            next_candidate = start_time + timedelta(weeks=1)
            ambiguities.append(
                Ambiguity(
                    field="begin_recurrence",
                    reason=(
                        f'"{recurrence_description}" implies an interval but '
                        "the starting week is not specified"
                    ),
                    options=[
                        start_time.strftime("%A %B %d, %Y"),
                        next_candidate.strftime("%A %B %d, %Y"),
                    ],
                )
            )

        # If there is recurrence but no end description, flag it.
        if not end_recurrence_description:
            ambiguities.append(
                Ambiguity(
                    field="end_recurrence_description",
                    reason="Recurring event has no end date specified",
                    options=["Add an end date", "Repeat indefinitely"],
                )
            )

    proposed = ProposedEvent(
        title=title,
        start_time=start_time,
        end_time=end_time,
        location=location,
        notes=text,
        recurrence_description=recurrence_description,
        begin_recurrence=begin_recurrence,
        end_recurrence_description=end_recurrence_description,
    )
    return proposed, ambiguities
