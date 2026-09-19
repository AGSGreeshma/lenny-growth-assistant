"""
POST /api/chat (app/api/chat.py): the unified router that classifies intent
(app/agent/orchestrator.py -- AGENT_SDK_ENABLED=false in conftest.py, so this
always exercises the deterministic heuristic classifier, never the real
Claude Agent SDK/network) and branches to plain Q&A, Ship 30 essay, or HTML
artifact generation. Retrieval and LLM generation are mocked throughout.
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
def test_chat_plain_question_grounded(client):
    session_id = _create_session(client)

    with patch.object(
        TranscriptRetriever, "retrieve_relevant_chunks", return_value=[_CHUNK]
    ), patch(
        "app.rag.generator.generate_with_fallback",
        new=AsyncMock(return_value=("Activation means...", "ollama")),
    ):
        response = client.post(
            "/api/chat", json={"session_id": session_id, "message": "What is activation?"}
        )

    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "chat"
    assert body["used_agent_sdk"] is False
    assert body["grounded"] is True
    assert body["answer"] == "Activation means..."
    assert body["artifact"] is None
    assert body["provider"] == "ollama"


@requires_db
def test_chat_plain_question_not_grounded_short_circuits_llm(client):
    session_id = _create_session(client)

    mock_generate = AsyncMock(return_value=("should not be called", "ollama"))
    with patch.object(
        TranscriptRetriever, "retrieve_relevant_chunks", return_value=[]
    ), patch("app.rag.generator.generate_with_fallback", new=mock_generate):
        response = client.post(
            "/api/chat",
            json={"session_id": session_id, "message": "an out-of-domain question"},
        )

    body = response.json()
    assert body["grounded"] is False
    assert body["provider"] == "none"
    assert "don't have enough grounded material" in body["answer"]
    mock_generate.assert_not_called()


@requires_db
def test_chat_routes_essay_intent_and_returns_markdown_artifact(client):
    session_id = _create_session(client)

    with patch.object(
        TranscriptRetriever, "retrieve_relevant_chunks", return_value=[_CHUNK]
    ), patch(
        "app.skills.ship30.generate_with_fallback",
        new=AsyncMock(return_value=("# Essay\n\nBody.", "ollama")),
    ):
        response = client.post(
            "/api/chat",
            json={
                "session_id": session_id,
                "message": "write a ship 30 essay about activation",
            },
        )

    body = response.json()
    assert body["intent"] == "essay"
    assert body["artifact"]["type"] == "markdown"
    assert body["artifact"]["content"] == "# Essay\n\nBody."


@requires_db
def test_chat_routes_html_artifact_intent_and_sanitizes(client):
    session_id = _create_session(client)
    raw_html = "<!DOCTYPE html><html><body><h1>Hi</h1><script>alert(1)</script></body></html>"

    with patch.object(
        TranscriptRetriever, "retrieve_relevant_chunks", return_value=[_CHUNK]
    ), patch(
        "app.skills.html_artifact.generate_with_fallback",
        new=AsyncMock(return_value=(raw_html, "ollama")),
    ):
        response = client.post(
            "/api/chat",
            json={"session_id": session_id, "message": "give me this as an HTML page"},
        )

    body = response.json()
    assert body["intent"] == "html_artifact"
    assert body["artifact"]["type"] == "html"
    assert "<script>" not in body["artifact"]["content"]


@requires_db
def test_chat_persists_user_and_assistant_messages(client):
    session_id = _create_session(client)

    with patch.object(
        TranscriptRetriever, "retrieve_relevant_chunks", return_value=[_CHUNK]
    ), patch(
        "app.rag.generator.generate_with_fallback",
        new=AsyncMock(return_value=("An answer.", "ollama")),
    ):
        client.post("/api/chat", json={"session_id": session_id, "message": "A question?"})

    history = client.get(f"/api/sessions/{session_id}").json()
    assert [m["role"] for m in history["messages"]] == ["user", "assistant"]
    assert history["messages"][0]["content"] == "A question?"
    assert history["messages"][1]["content"] == "An answer."


@requires_db
def test_chat_uses_first_message_as_session_title(client):
    session_id = _create_session(client)

    with patch.object(
        TranscriptRetriever, "retrieve_relevant_chunks", return_value=[_CHUNK]
    ), patch(
        "app.rag.generator.generate_with_fallback",
        new=AsyncMock(return_value=("An answer.", "ollama")),
    ):
        client.post(
            "/api/chat", json={"session_id": session_id, "message": "What drives retention?"}
        )

    history = client.get(f"/api/sessions/{session_id}").json()
    assert history["title"] == "What drives retention?"


@requires_db
def test_chat_rejects_empty_message(client):
    session_id = _create_session(client)

    response = client.post("/api/chat", json={"session_id": session_id, "message": "   "})

    assert response.status_code == 400


@requires_db
def test_chat_returns_404_for_unknown_session(client):
    response = client.post(
        "/api/chat",
        json={"session_id": "00000000-0000-0000-0000-000000000000", "message": "hi"},
    )

    assert response.status_code == 404
