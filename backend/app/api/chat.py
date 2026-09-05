import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DbSession

from app.database import get_db
from app.models.db_models import ChatSession, ChatMessage
from app.models.schemas import ChatRequest, ChatResponse, Source
from app.rag.retriever import TranscriptRetriever
from app.rag.generator import generate_answer

logger = logging.getLogger("lenny-assistant")

router = APIRouter(prefix="/api/chat", tags=["chat"])


def to_source(chunk: dict) -> Source:
    return Source(
        episode=chunk.get("episode") or chunk.get("episode_title") or "Unknown Episode",
        guest=chunk.get("guest") or chunk.get("guest_name") or chunk.get("speaker") or "Unknown Guest",
        timestamp=chunk.get("timestamp") or chunk.get("timestamp_ref") or "N/A",
        score=chunk.get("score") or 0.0,
        url=chunk.get("url"),
    )


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

    try:
        retriever = TranscriptRetriever(db)
        chunks = retriever.retrieve_relevant_chunks(message, top_k=5)
    except Exception:
        logger.exception("Retrieval failed")
        raise HTTPException(status_code=502, detail="Retrieval step failed. Check DB connection.")

    try:
        answer = await generate_answer(message, chunks, history=history)
    except Exception:
        logger.exception("Generation failed")
        raise HTTPException(status_code=502, detail="LLM generation failed. Check Ollama/API is running and responsive.")

    is_grounded = bool(chunks) and "do not provide enough information" not in answer
    sources = [to_source(c) for c in chunks] if is_grounded else []

    assistant_msg = ChatMessage(
        session_id=request.session_id,
        role="assistant",
        content=answer,
        sources=[s.model_dump() for s in sources],
    )
    db.add(assistant_msg)
    db.commit()

    return ChatResponse(
        session_id=request.session_id,
        answer=answer,
        grounded=is_grounded,
        sources=sources,
    )