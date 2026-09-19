from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class Source(BaseModel):
    episode: str = "Unknown Episode"
    guest: str = "Unknown Guest"
    timestamp: str = "N/A"
    score: float = 0.0
    url: str | None = None


class SessionCreateRequest(BaseModel):
    # Optional, anonymous client label (e.g. browser user-agent) -- there is
    # no authentication in this app's scope (documented in the PRD), so this
    # is the "user metadata" the assignment asks to persist: enough to tell
    # sessions apart by originating client without identifying a person.
    client_label: str | None = Field(default=None, max_length=300)


class SessionCreateResponse(BaseModel):
    session_id: UUID
    title: str | None = None
    created_at: datetime
    client_label: str | None = None


class MessageOut(BaseModel):
    role: str
    content: str
    sources: list[dict] | None = None
    artifact_type: str | None = None
    created_at: datetime

    class Config:
        from_attributes = True


class SessionHistoryResponse(BaseModel):
    session_id: UUID
    title: str | None = None
    messages: list[MessageOut]


class ChatRequest(BaseModel):
    session_id: UUID
    message: str = Field(..., min_length=1, max_length=2000)
    # Optional per-request override for the frontend's provider toggle. None
    # (the default) means "use FORCE_LLM_PROVIDER / the normal Ollama-first,
    # OpenAI-fallback behavior" -- see app/llm/router.py.
    provider: Literal["ollama", "openai"] | None = None


class Artifact(BaseModel):
    type: str  # "markdown" | "html"
    title: str
    content: str


class ChatResponse(BaseModel):
    session_id: UUID
    answer: str
    grounded: bool
    sources: list[Source]
    provider: str = "ollama"
    # Agent-layer routing metadata (app/agent/orchestrator.py): which intent
    # the request was routed to, and whether that routing decision was made
    # by the Claude Agent SDK or by the offline heuristic fallback.
    intent: str = "chat"
    used_agent_sdk: bool = False
    # Populated when the routed intent produced a Ship30 essay or HTML
    # artifact directly from a chat message (as opposed to the dedicated
    # /api/essay button), so the frontend can open the Artifact Viewer
    # without a second request.
    artifact: Artifact | None = None


class EssayRequest(BaseModel):
    session_id: UUID
    topic: str = Field(..., min_length=1, max_length=500)
    provider: Literal["ollama", "openai"] | None = None


class EssayResponse(BaseModel):
    session_id: UUID
    essay: str
    sources: list[Source]
    provider: str = "ollama"


class ArtifactRequest(BaseModel):
    session_id: UUID
    topic: str = Field(..., min_length=1, max_length=500)
    provider: Literal["ollama", "openai"] | None = None


class ArtifactResponse(BaseModel):
    session_id: UUID
    artifact: Artifact
    sources: list[Source]
    provider: str = "ollama"
