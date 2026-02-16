# Event Lifecycle Service

A small FastAPI service that converts **unstructured event text** into
**structured events**, tracks their lifecycle status, and fires reminders
via a simulated clock.

## Quick start

```bash
# 1. Create & activate a virtualenv (Python 3.11+)
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set your OpenAI API key
export OPENAI_API_KEY="sk-..."

# 4. Run the server
uvicorn app.main:app --reload

# 5. Run tests
pytest
```

The `POST /parse` endpoint uses **OpenAI's `gpt-4o-mini`** model to extract structured event fields from free-form text. You must have a valid [OpenAI API key](https://platform.openai.com/api-keys) set in the `OPENAI_API_KEY` environment variable before starting the server. Without it, parse requests will fail.

The server starts at **http://127.0.0.1:8000**.
Interactive API docs are available at **http://127.0.0.1:8000/docs**.

## How it works

1. **Parse** — Send unstructured text to `POST /parse`. The server extracts a proposed event, flags any ambiguities (e.g. "7pm — AM or PM?", missing end time), checks for scheduling conflicts against existing events, and returns a `ParseResponse` with status `pending`.

2. **Review** — Call `GET /proposed-events` to see all pending proposed events. Each entry includes the parsed event fields, a list of ambiguities that need resolution, and any detected conflicts with confirmed or other pending events.

3. **Confirm or reject** — For each proposed event the client decides:
   - `POST /proposed-events/{id}/confirm` — send back the (possibly ambiguity-resolved) `ProposedEvent`. The server creates a confirmed `Event`, marks the `ParseResponse` as `confirmed`, and removes it from the pending queue.
   - `POST /proposed-events/{id}/reject` — marks the `ParseResponse` as `rejected`. No `Event` is created, but the record is kept so a user can revisit old proposals later.

4. **Browse confirmed events** — `GET /events` returns all confirmed events. `GET /events/{id}` returns a single event.

5. **Reminders** — `POST /tick` advances the simulated clock and fires any reminders that are due.

## API endpoints

### `POST /parse` — parse unstructured text into a proposed event

Send a blob of free-form text. The server parses it into a `ProposedEvent`, detects ambiguities and conflicts, stores the result as a `ParseResponse` with status `pending`, and returns it.

```bash
curl -X POST http://127.0.0.1:8000/parse \
  -H "Content-Type: application/json" \
  -d '{"text": "Dinner with Alice tomorrow at 7pm at Olive Garden"}'
```

**Response** (abbreviated):
```json
{
  "id": "abc-123",
  "status": "pending",
  "proposed_event": {
    "title": "Dinner with Alice",
    "start_time": "2025-06-15T19:00:00Z",
    "end_time": "2025-06-15T20:00:00Z",
    "location": "Olive Garden"
  },
  "ambiguities": [
    { "field": "end_time", "reason": "No end time specified; defaulted to 1 hour", "options": [] }
  ],
  "conflicts": []
}
```

### `GET /proposed-events` — list pending proposed events

Returns all `ParseResponse` objects that are still `pending`. Use this to show the user what needs to be confirmed or rejected.

```bash
curl http://127.0.0.1:8000/proposed-events
```

### `POST /proposed-events/{id}/confirm` — confirm a proposed event

Send the final `ProposedEvent` (with any ambiguities resolved by the user) in the request body. The server creates a confirmed `Event`, marks the `ParseResponse` as `confirmed`, and publishes an `EventCreated` domain event (which triggers reminders, conflict checks, etc.).

```bash
curl -X POST http://127.0.0.1:8000/proposed-events/abc-123/confirm \
  -H "Content-Type: application/json" \
  -d '{
    "proposed_event": {
      "title": "Dinner with Alice",
      "start_time": "2025-06-15T19:00:00Z",
      "end_time": "2025-06-15T20:30:00Z",
      "location": "Olive Garden"
    }
  }'
```

### `POST /proposed-events/{id}/reject` — reject a proposed event

Marks the `ParseResponse` as `rejected`. No `Event` is created. The rejected record is persisted so a user can revisit it later.

```bash
curl -X POST http://127.0.0.1:8000/proposed-events/abc-123/reject
```

### `GET /events` — list all confirmed events

```bash
curl http://127.0.0.1:8000/events
```

### `GET /events/{id}` — get a single event by id

```bash
curl http://127.0.0.1:8000/events/SOME-UUID-HERE
```

### `POST /tick` — advance simulated time and fire due reminders

```bash
# Use server's current UTC time
curl -X POST http://127.0.0.1:8000/tick

# Or supply an explicit time
curl -X POST "http://127.0.0.1:8000/tick?now=2025-06-15T18:45:00"
```

## Project structure

```
app/
  main.py              # FastAPI app, routes, singleton wiring
  domain/
    models.py          # Pydantic domain models (StructuredEvent, Reminder, …)
    events.py          # Domain event classes (EventCreated, ConflictDetected, …)
    bus.py             # Synchronous in-process event bus
    handlers.py        # Domain event handlers
  services/
    parser.py          # Natural-language → StructuredEvent parser
    conflicts.py       # Overlap / conflict detection
    reminders.py       # Reminder creation and firing logic
  repos/
    memory.py          # In-memory dict/list repositories
tests/
  test_parser_smoke.py # Smoke tests for the parser
  test_conflicts.py    # Conflict detection tests
  test_lifecycle.py    # Integration tests via FastAPI TestClient
```

## What's mocked vs. functional

| Component | Status |
|---|---|
| Domain models (`Event`, `ProposedEvent`, `ParseResponse`, etc.) | **Functional** — fully defined Pydantic v2 models |
| Event bus (`EventBus`) | **Functional** — synchronous pub/sub works end-to-end |
| In-memory repositories | **Functional** — dict/list-backed stores for events, parse responses, reminders |
| `POST /parse` | **Functional** — parses text, detects ambiguities & conflicts, stores as pending |
| `GET /proposed-events` | **Functional** — returns pending parse responses |
| `POST /proposed-events/{id}/confirm` | **Functional** — creates confirmed event, publishes domain event |
| `POST /proposed-events/{id}/reject` | **Functional** — marks parse response as rejected |
| `GET /events`, `GET /events/{id}` | **Functional** — reads from in-memory repo |
| Conflict detection | **Functional** — checks overlaps against confirmed and pending events |
| Domain event handlers | **Functional** — handler registry wired at startup |
| `POST /tick` | **Functional** — fires due reminders via the event bus |

## Next steps for production

1. **Replace `/tick`** with a real background scheduler (APScheduler, Celery, or `asyncio` tasks).
2. **Add status filtering to `GET /proposed-events`** — allow querying by `pending`, `confirmed`, `rejected`.
3. **Add authentication & authorization** (OAuth 2 / API keys).
4. **Add structured logging** and **observability** (OpenTelemetry).
5. **Containerize** with Docker and add a CD pipeline.
