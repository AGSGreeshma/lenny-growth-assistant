from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DbSession

from app.database import get_db
from app.models.db_models import ChatSession, ChatMessage
from app.models.schemas import (
    SessionCreateRequest,
    SessionCreateResponse,
    SessionHistoryResponse,
)

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.post("", response_model=SessionCreateResponse)
def create_session(
    request: SessionCreateRequest | None = None,
    db: DbSession = Depends(get_db),
):
    client_label = (request.client_label if request else None) or None
    session = ChatSession(client_label=client_label)
    db.add(session)
    db.commit()
    db.refresh(session)
    return SessionCreateResponse(
        session_id=session.id,
        title=session.title,
        created_at=session.created_at,
        client_label=session.client_label,
    )


@router.get("/{session_id}", response_model=SessionHistoryResponse)
def get_session_history(session_id: str, db: DbSession = Depends(get_db)):
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")

    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )

    return SessionHistoryResponse(
        session_id=session.id,
        title=session.title,
        messages=messages,
    )
