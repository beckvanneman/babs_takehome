"""Integration tests exercising the full event lifecycle via the FastAPI app."""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture()
def client():
    return TestClient(app)


def test_list_events_empty(client: TestClient):
    response = client.get("/events")
    assert response.status_code == 200
    assert response.json() == []


def test_get_event_not_found(client: TestClient):
    response = client.get("/events/nonexistent")
    assert response.status_code == 404


def test_tick_returns_time(client: TestClient):
    response = client.post("/tick")
    assert response.status_code == 200
    body = response.json()
    assert "time" in body
    assert "reminders_fired" in body
