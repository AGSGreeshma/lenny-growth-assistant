import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DbSession

from app.config import RAG_MIN_SIMILARITY
from app.database import get_db
from app.models.db_models import ChatSession, ChatMessage
from app.models.schemas import EssayRequest, EssayResponse, Source
from app.llm.router import GenerationTimeoutError
from app.rag.generator import NOT_GROUNDED_MESSAGE
from app.rag.retriever import TranscriptRetriever
from app.skills.ship30 import generate_ship30_essay

logger = logging.getLogger("lenny-assistant")

router = APIRouter(prefix="/api/essay", tags=["essay"])

_ESSAY_TOP_K = 6


def to_source(chunk: dict) -> Source:
    return Source(
        episode=chunk.get("episode")
        or chunk.get("episode_title")
        or "Unknown Episode",
        guest=chunk.get("guest")
        or chunk.get("guest_name")
        or chunk.get("speaker")
        or "Unknown Guest",
        timestamp=chunk.get("timestamp")
        or chunk.get("timestamp_ref")
        or "N/A",
        score=chunk.get("score") or 0.0,
        url=chunk.get("url"),
    )


@router.post("", response_model=EssayResponse)
async def create_essay(
    request: EssayRequest,
    db: DbSession = Depends(get_db),
):
    session = (
        db.query(ChatSession)
        .filter(ChatSession.id == request.session_id)
        .first()
    )

    if not session:
        raise HTTPException(
            status_code=404,
            detail="Session not found. Create one via POST /api/sessions first.",
        )

    topic = request.topic.strip()

    if not topic:
        raise HTTPException(
            status_code=400,
            detail="Topic cannot be empty.",
        )

    try:
        retriever = TranscriptRetriever(db)
        chunks = retriever.retrieve_relevant_chunks(
            topic, top_k=_ESSAY_TOP_K, min_similarity=RAG_MIN_SIMILARITY
        )

    except Exception as exc:
        logger.exception("Retrieval failed")
        raise HTTPException(
            status_code=502,
            detail="Retrieval step failed. Check DB connection.",
        ) from exc

    if not chunks:
        # Nothing above the relevance floor -- refuse to write an essay that
        # would have to be invented rather than grounded (see
        # app/rag/retriever.py's DEFAULT_MIN_SIMILARITY).
        return EssayResponse(
            session_id=request.session_id,
            essay=NOT_GROUNDED_MESSAGE,
            sources=[],
            provider="none",
        )

    try:
        essay, provider = await generate_ship30_essay(topic, chunks, force_provider=request.provider)

    except GenerationTimeoutError as exc:
        logger.warning("Essay generation timed out: %s", exc)
        raise HTTPException(status_code=504, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Essay generation failed")
        raise HTTPException(
            status_code=502,
            detail="Essay generation failed. Check Ollama/OpenAI configuration.",
        ) from exc

    sources = [to_source(chunk) for chunk in chunks]

    # Persisted as a message with artifact_type="markdown" so it shows up in
    # session history and can be distinguished from a normal chat reply.
    artifact_msg = ChatMessage(
        session_id=request.session_id,
        role="assistant",
        content=essay,
        sources=[source.model_dump() for source in sources],
        artifact_type="markdown",
    )

    db.add(artifact_msg)
    db.commit()

    return EssayResponse(
        session_id=request.session_id,
        essay=essay,
        sources=sources,
        provider=provider,
    )
