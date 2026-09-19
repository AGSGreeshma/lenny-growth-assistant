"""
POST /api/artifact (app/api/artifact.py). Retrieval and LLM generation are
mocked; the raw "LLM output" here deliberately includes a <script> tag to
confirm the sanitizer (app/skills/html_artifact.py) runs on this path too,
not just in its own unit tests.
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

_RAW_HTML_WITH_SCRIPT = (
    "<!DOCTYPE html><html><head><style>body{font-family:sans-serif}</style></head>"
    "<body><h1>Activation</h1><script>alert('x')</script></body></html>"
)


def _create_session(client):
    return client.post("/api/sessions", json={}).json()["session_id"]


@requires_db
def test_artifact_returns_not_grounded_message_when_no_chunks_found(client):
    session_id = _create_session(client)

    with patch.object(TranscriptRetriever, "retrieve_relevant_chunks", return_value=[]):
        response = client.post(
            "/api/artifact", json={"session_id": session_id, "topic": "an out-of-domain topic"}
        )

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "none"
    assert body["artifact"]["type"] == "markdown"
    assert "don't have enough grounded material" in body["artifact"]["content"]


@requires_db
def test_artifact_generates_sanitizes_and_persists_when_grounded(client):
    session_id = _create_session(client)

    with patch.object(
        TranscriptRetriever, "retrieve_relevant_chunks", return_value=[_CHUNK]
    ), patch(
        "app.skills.html_artifact.generate_with_fallback",
        new=AsyncMock(return_value=(_RAW_HTML_WITH_SCRIPT, "ollama")),
    ):
        response = client.post(
            "/api/artifact", json={"session_id": session_id, "topic": "activation strategies"}
        )

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "ollama"
    assert body["artifact"]["type"] == "html"
    assert "<script>" not in body["artifact"]["content"]
    assert "<h1>Activation</h1>" in body["artifact"]["content"]

    history = client.get(f"/api/sessions/{session_id}").json()
    assert history["messages"][0]["artifact_type"] == "html"
    assert "<script>" not in history["messages"][0]["content"]


@requires_db
def test_artifact_rejects_empty_topic(client):
    session_id = _create_session(client)

    response = client.post("/api/artifact", json={"session_id": session_id, "topic": ""})

    assert response.status_code == 400


@requires_db
def test_artifact_returns_404_for_unknown_session(client):
    response = client.post(
        "/api/artifact",
        json={"session_id": "00000000-0000-0000-0000-000000000000", "topic": "onboarding"},
    )

    assert response.status_code == 404
