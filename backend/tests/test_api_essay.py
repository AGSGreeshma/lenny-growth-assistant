"""
POST /api/essay (app/api/essay.py). Retrieval and LLM generation are mocked
so this exercises routing/persistence/grounding logic only, never a real
embedding model, database vector search, Ollama, or OpenAI call.
"""

from unittest.mock import AsyncMock, patch

from app.rag.retriever import TranscriptRetriever
from tests.conftest import requires_db

_CHUNK = {
    "episode": "Growth 101",
    "url": "https://example.com/ep1",
    "text": "Some grounded transcript text about activation.",
    "speaker": "Guest Name",
    "timestamp": "00:05:00",
    "score": 0.87,
}


def _create_session(client):
    return client.post("/api/sessions", json={}).json()["session_id"]


@requires_db
def test_essay_returns_not_grounded_message_when_no_chunks_found(client):
    session_id = _create_session(client)

    with patch.object(TranscriptRetriever, "retrieve_relevant_chunks", return_value=[]):
        response = client.post(
            "/api/essay", json={"session_id": session_id, "topic": "an out-of-domain topic"}
        )

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "none"
    assert body["sources"] == []
    assert "don't have enough grounded material" in body["essay"]


@requires_db
def test_essay_generates_and_persists_when_grounded(client):
    session_id = _create_session(client)

    with patch.object(
        TranscriptRetriever, "retrieve_relevant_chunks", return_value=[_CHUNK]
    ), patch("app.skills.ship30.generate_with_fallback", new=AsyncMock(return_value=("# The Essay\n\nBody.", "ollama"))):
        response = client.post(
            "/api/essay", json={"session_id": session_id, "topic": "activation strategies"}
        )

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "ollama"
    assert body["essay"] == "# The Essay\n\nBody."
    assert len(body["sources"]) == 1
    assert body["sources"][0]["episode"] == "Growth 101"

    history = client.get(f"/api/sessions/{session_id}").json()
    assert len(history["messages"]) == 1
    assert history["messages"][0]["artifact_type"] == "markdown"


@requires_db
def test_essay_rejects_empty_topic(client):
    session_id = _create_session(client)

    response = client.post("/api/essay", json={"session_id": session_id, "topic": "   "})

    assert response.status_code == 400


@requires_db
def test_essay_returns_404_for_unknown_session(client):
    response = client.post(
        "/api/essay",
        json={"session_id": "00000000-0000-0000-0000-000000000000", "topic": "onboarding"},
    )

    assert response.status_code == 404
