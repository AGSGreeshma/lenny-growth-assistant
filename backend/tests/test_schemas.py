"""
Pydantic schema validation (app/models/schemas.py): request-size limits,
defaults, and the ChatResponse/Artifact shapes the frontend and API tests
both depend on.
"""

import uuid

import pytest
from pydantic import ValidationError

from app.models.schemas import (
    Artifact,
    ChatRequest,
    ChatResponse,
    EssayRequest,
    Source,
)


def test_chat_request_rejects_empty_message():
    with pytest.raises(ValidationError):
        ChatRequest(session_id=uuid.uuid4(), message="")


def test_chat_request_rejects_message_over_max_length():
    with pytest.raises(ValidationError):
        ChatRequest(session_id=uuid.uuid4(), message="x" * 2001)


def test_chat_request_accepts_message_at_max_length():
    request = ChatRequest(session_id=uuid.uuid4(), message="x" * 2000)
    assert len(request.message) == 2000


def test_essay_request_rejects_empty_topic():
    with pytest.raises(ValidationError):
        EssayRequest(session_id=uuid.uuid4(), topic="")


def test_source_has_safe_defaults():
    source = Source()
    assert source.episode == "Unknown Episode"
    assert source.guest == "Unknown Guest"
    assert source.timestamp == "N/A"
    assert source.score == 0.0
    assert source.url is None


def test_chat_response_defaults_to_chat_intent_with_no_artifact():
    response = ChatResponse(
        session_id=uuid.uuid4(),
        answer="hello",
        grounded=True,
        sources=[],
    )
    assert response.intent == "chat"
    assert response.used_agent_sdk is False
    assert response.artifact is None
    assert response.provider == "ollama"


def test_chat_response_carries_artifact_when_present():
    response = ChatResponse(
        session_id=uuid.uuid4(),
        answer="Here's your essay",
        grounded=True,
        sources=[],
        intent="essay",
        artifact=Artifact(type="markdown", title="My Essay", content="# Essay"),
    )
    assert response.artifact.type == "markdown"
    assert response.artifact.content == "# Essay"


def test_artifact_requires_type_title_and_content():
    with pytest.raises(ValidationError):
        Artifact(type="html")
