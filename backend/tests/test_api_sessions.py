"""
POST /api/sessions and GET /api/sessions/{id} against a real Postgres+pgvector
test database (see conftest.py's `requires_db`/`client` fixtures). No LLM or
retrieval calls happen on this path, so nothing needs mocking.
"""

import pytest

from tests.conftest import requires_db


@requires_db
def test_create_session_without_client_label(client):
    response = client.post("/api/sessions", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["title"] is None
    assert body["client_label"] is None
    assert "session_id" in body


@requires_db
def test_create_session_with_client_label(client):
    response = client.post("/api/sessions", json={"client_label": "chrome/macos demo"})

    assert response.status_code == 200
    assert response.json()["client_label"] == "chrome/macos demo"


@requires_db
def test_create_session_with_empty_body(client):
    response = client.post("/api/sessions")

    assert response.status_code == 200
    assert response.json()["client_label"] is None


@requires_db
def test_get_session_history_for_new_session_is_empty(client):
    created = client.post("/api/sessions", json={}).json()

    response = client.get(f"/api/sessions/{created['session_id']}")

    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == created["session_id"]
    assert body["messages"] == []


@requires_db
def test_get_session_history_for_unknown_session_returns_404(client):
    response = client.get("/api/sessions/00000000-0000-0000-0000-000000000000")

    assert response.status_code == 404
