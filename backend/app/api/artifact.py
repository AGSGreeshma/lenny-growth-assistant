"""Dedicated endpoint for on-demand HTML/CSS artifact generation -- the
HTML/CSS counterpart to /api/essay's Markdown generation. Kept as its own
route (mirroring essay.py) so the frontend can offer an explicit "Make HTML
artifact" action, in addition to the chat-routed path in app/api/chat.py
where the agent infers this intent from a natural-language request."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DbSession

from app.config import RAG_MIN_SIMILARITY
from app.database import get_db
from app.llm.router import GenerationTimeoutError
from app.models.db_models import ChatSession, ChatMessage
from app.models.schemas import Artifact, ArtifactRequest, ArtifactResponse, Source
from app.rag.generator import NOT_GROUNDED_MESSAGE
from app.rag.retriever import TranscriptRetriever
from app.skills.html_artifact import generate_html_artifact

logger = logging.getLogger("lenny-assistant")

router = APIRouter(prefix="/api/artifact", tags=["artifact"])

_ARTIFACT_TOP_K = 6


def to_source(chunk: dict) -> Source:
    return Source(
        episode=chunk.get("episode") or chunk.get("episode_title") or "Unknown Episode",
        guest=chunk.get("guest") or chunk.get("guest_name") or chunk.get("speaker") or "Unknown Guest",
        timestamp=chunk.get("timestamp") or chunk.get("timestamp_ref") or "N/A",
        score=chunk.get("score") or 0.0,
        url=chunk.get("url"),
    )


@router.post("", response_model=ArtifactResponse)
async def create_html_artifact(request: ArtifactRequest, db: DbSession = Depends(get_db)):
    session = db.query(ChatSession).filter(ChatSession.id == request.session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found. Create one via POST /api/sessions first.")

    topic = request.topic.strip()
    if not topic:
        raise HTTPException(status_code=400, detail="Topic cannot be empty.")

    try:
        retriever = TranscriptRetriever(db)
        chunks = retriever.retrieve_relevant_chunks(
            topic, top_k=_ARTIFACT_TOP_K, min_similarity=RAG_MIN_SIMILARITY
        )
    except Exception as exc:
        logger.exception("Retrieval failed")
        raise HTTPException(status_code=502, detail="Retrieval step failed. Check DB connection.") from exc

    if not chunks:
        return ArtifactResponse(
            session_id=request.session_id,
            artifact=Artifact(type="markdown", title="Not enough grounded material", content=NOT_GROUNDED_MESSAGE),
            sources=[],
            provider="none",
        )

    try:
        html, provider = await generate_html_artifact(topic, chunks, force_provider=request.provider)
    except GenerationTimeoutError as exc:
        logger.warning("Artifact generation timed out: %s", exc)
        raise HTTPException(status_code=504, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("HTML artifact generation failed")
        raise HTTPException(
            status_code=502, detail="Artifact generation failed. Check Ollama/OpenAI configuration."
        ) from exc

    sources = [to_source(chunk) for chunk in chunks]
    artifact = Artifact(type="html", title=topic[:60], content=html)

    artifact_msg = ChatMessage(
        session_id=request.session_id,
        role="assistant",
        content=html,
        sources=[s.model_dump() for s in sources],
        artifact_type="html",
    )
    db.add(artifact_msg)
    db.commit()

    return ArtifactResponse(
        session_id=request.session_id,
        artifact=artifact,
        sources=sources,
        provider=provider,
    )
