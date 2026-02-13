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

# 3. Run the server
uvicorn app.main:app --reload

# 4. Run tests
pytest
```

The server starts at **http://127.0.0.1:8000**.
Interactive API docs are available at **http://127.0.0.1:8000/docs**.

## API endpoints

### `POST /parse` — parse unstructured text into a structured event

```bash
curl -X POST http://127.0.0.1:8000/parse \
  -H "Content-Type: application/json" \
  -d '{"raw_text": "Dinner with Alice tomorrow at 7pm at Olive Garden"}'
```

### `GET /events` — list all structured events

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
| Domain models (`StructuredEvent`, `Reminder`, etc.) | **Functional** — fully defined Pydantic v2 models |
| Event bus (`EventBus`) | **Functional** — synchronous pub/sub works end-to-end |
| In-memory repositories | **Functional** — dict/list-backed `save`, `get`, `list_all` |
| `GET /events`, `GET /events/{id}` | **Functional** — reads from in-memory repo |
| `POST /tick` | **Functional** (stub) — returns current time, fires no reminders yet |
| `POST /parse` | **Placeholder** — returns 501; parser service raises `NotImplementedError` |
| Conflict detection | **Placeholder** — raises `NotImplementedError` |
| Reminder creation & firing | **Placeholder** — raises `NotImplementedError` |
| Domain event handlers | **Placeholder** — `on_event_created` is a no-op |

## Next steps for production

1. **Implement the parser service** — use `dateparser` to extract dates, regex/heuristics for title and location, and persist via the event repo.
2. **Implement conflict detection** — compare time ranges with existing events and publish `ConflictDetected` domain events.
3. **Implement reminder logic** — generate default reminders on event creation; fire them when `/tick` advances past `remind_at`.
4. **Wire domain event handlers** — subscribe handlers to the bus at startup so that creating an event automatically schedules reminders and checks conflicts.
5. **Replace `/tick`** with a real background scheduler (APScheduler, Celery, or `asyncio` tasks).
6. **Add authentication & authorization** (OAuth 2 / API keys).
7. **Add structured logging** and **observability** (OpenTelemetry).
8. **Containerize** with Docker and add a CI pipeline.
