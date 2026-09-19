import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DbSession

from app.agent.orchestrator import classify_intent
from app.config import RAG_MIN_SIMILARITY
from app.database import get_db
from app.models.db_models import ChatSession, ChatMessage
from app.models.schemas import Artifact, ChatRequest, ChatResponse, Source
from app.rag.generator import NOT_GROUNDED_MESSAGE, generate_answer
from app.rag.retriever import TranscriptRetriever
from app.skills.html_artifact import generate_html_artifact
from app.skills.ship30 import generate_ship30_essay

logger = logging.getLogger("lenny-assistant")

router = APIRouter(prefix="/api/chat", tags=["chat"])

_ESSAY_TOP_K = 6
_CHAT_TOP_K = 5


def to_source(chunk: dict) -> Source:
    return Source(
        episode=chunk.get("episode") or chunk.get("episode_title") or "Unknown Episode",
        guest=chunk.get("guest") or chunk.get("guest_name") or chunk.get("speaker") or "Unknown Guest",
        timestamp=chunk.get("timestamp") or chunk.get("timestamp_ref") or "N/A",
        score=chunk.get("score") or 0.0,
        url=chunk.get("url"),
    )


def _retrieve(db: DbSession, query: str, top_k: int) -> list[dict]:
    try:
        retriever = TranscriptRetriever(db)
        return retriever.retrieve_relevant_chunks(query, top_k=top_k, min_similarity=RAG_MIN_SIMILARITY)
    except Exception as exc:
        logger.exception("Retrieval failed")
        raise HTTPException(
            status_code=502, detail="Retrieval step failed. Check DB connection."
        ) from exc


@router.post("", response_model=ChatResponse)
async def chat(request: ChatRequest, db: DbSession = Depends(get_db)):
    session = db.query(ChatSession).filter(ChatSession.id == request.session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found. Create one via POST /api/sessions first.")

    message = request.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    # Prior turns for this session, oldest first -- gives the model
    # conversational continuity for follow-up questions.
    prior_messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == request.session_id)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )
    history = [{"role": m.role, "content": m.content} for m in prior_messages]

    # Persist the user's message before generating, so it's saved even if
    # generation subsequently fails.
    user_msg = ChatMessage(session_id=request.session_id, role="user", content=message)
    db.add(user_msg)
    db.commit()

    # Use the session's first message as its title, for the sidebar (planned UI).
    if session.title is None:
        session.title = message[:80]
        db.commit()

    # Agent layer: decide whether this is a plain grounded question, a Ship
    # 30 for 30 essay request, or an HTML/CSS artifact request. See
    # app/agent/orchestrator.py for why routing (not answer-writing) is what
    # runs through the Claude Agent SDK.
    routing = await classify_intent(message, db)

    artifact: Artifact | None = None

    try:
        if routing.intent == "essay":
            chunks = _retrieve(db, routing.topic, _ESSAY_TOP_K)
            if not chunks:
                answer, provider = NOT_GROUNDED_MESSAGE, "none"
            else:
                essay, provider = await generate_ship30_essay(
                    routing.topic, chunks, force_provider=request.provider
                )
                artifact = Artifact(
                    type="markdown",
                    title=f"Ship 30 for 30: {routing.topic[:60]}",
                    content=essay,
                )
                answer = "Here's your Ship 30 for 30 essay -- opened in the Artifact Viewer."

        elif routing.intent == "html_artifact":
            chunks = _retrieve(db, routing.topic, _ESSAY_TOP_K)
            if not chunks:
                answer, provider = NOT_GROUNDED_MESSAGE, "none"
            else:
                html, provider = await generate_html_artifact(
                    routing.topic, chunks, force_provider=request.provider
                )
                artifact = Artifact(
                    type="html",
                    title=routing.topic[:60],
                    content=html,
                )
                answer = "Here's your HTML artifact -- opened in the Artifact Viewer (sandboxed)."

        else:
            chunks = _retrieve(db, message, _CHAT_TOP_K)
            answer, provider = await generate_answer(
                message, chunks, history=history, force_provider=request.provider
            )

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Generation failed")
        raise HTTPException(
            status_code=502,
            detail="LLM generation failed. Check Ollama/API is running and responsive.",
        ) from exc

    is_grounded = bool(chunks)
    sources = [to_source(c) for c in chunks] if is_grounded else []

    assistant_msg = ChatMessage(
        session_id=request.session_id,
        role="assistant",
        content=artifact.content if artifact else answer,
        sources=[s.model_dump() for s in sources],
        artifact_type=artifact.type if artifact else None,
    )
    db.add(assistant_msg)
    db.commit()

    return ChatResponse(
        session_id=request.session_id,
        answer=answer,
        grounded=is_grounded,
        sources=sources,
        provider=provider,
        intent=routing.intent,
        used_agent_sdk=routing.used_agent_sdk,
        artifact=artifact,
    )
