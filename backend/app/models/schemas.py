from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class Source(BaseModel):
    episode: str = "Unknown Episode"
    guest: str = "Unknown Guest"
    timestamp: str = "N/A"
    score: float = 0.0
    url: str | None = None


class SessionCreateResponse(BaseModel):
    session_id: UUID
    title: str | None = None
    created_at: datetime


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


class ChatResponse(BaseModel):
    session_id: UUID
    answer: str
    grounded: bool
    sources: list[Source]


class EssayRequest(BaseModel):
    session_id: UUID
    topic: str = Field(..., min_length=1, max_length=500)


class EssayResponse(BaseModel):
    session_id: UUID
    essay: str
    sources: list[Source]