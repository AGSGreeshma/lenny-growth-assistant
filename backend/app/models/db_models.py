import uuid

from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from pgvector.sqlalchemy import Vector

from app.database import Base


class TranscriptChunk(Base):
    __tablename__ = "transcript_chunks"

    id = Column(Integer, primary_key=True, index=True)

    episode_title = Column(String, nullable=False)
    episode_url = Column(String, nullable=True)

    chunk_text = Column(Text, nullable=False)

    speaker = Column(String, nullable=True)
    timestamp = Column(String, nullable=True)

    embedding = Column(Vector(384), nullable=False)


class ChatSession(Base):
    __tablename__ = "sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ChatMessage(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String, nullable=False)  # "user" | "assistant"
    content = Column(Text, nullable=False)
    sources = Column(JSONB, nullable=True)
    artifact_type = Column(String, nullable=True)  # e.g. "markdown" for Ship30 essays
    created_at = Column(DateTime(timezone=True), server_default=func.now())