import logging
import os

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db
from app.rag.retriever import TranscriptRetriever
from app.rag.generator import generate_answer
from app.api import sessions, chat, essay

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("lenny-assistant")

app = FastAPI(
    title="Lenny Growth Assistant",
    description="RAG-powered assistant for Lenny's Podcast transcripts",
)

extra_origins = os.environ.get("CORS_ORIGINS", "")
allow_origins = [
    "http://localhost:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
    "http://localhost:5175",
    "http://127.0.0.1:5175",
] + [o.strip() for o in extra_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):5\d{3}",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)


class Source(BaseModel):
    episode: str = "Unknown Episode"
    guest: str = "Unknown Guest"
    timestamp: str = "N/A"
    score: float = 0.0
    url: str | None = None


class AskResponse(BaseModel):
    answer: str
    grounded: bool
    sources: list[Source]


app.include_router(sessions.router)
app.include_router(chat.router)
app.include_router(essay.router)


@app.get("/")
def root():
    return {"message": "Lenny Growth Assistant API is running!"}


@app.get("/api/health")
def health(db: Session = Depends(get_db)):
    status = {"api": "ok", "db": "unknown"}
    try:
        db.execute(text("SELECT 1"))
        status["db"] = "ok"
    except Exception as exc:
        logger.exception("Health check DB error")
        status["db"] = f"error: {exc}"
    return status


def to_source(chunk: dict) -> Source:
    """Builds a Source safely no matter what keys/None values retriever.py returns."""
    return Source(
        episode=chunk.get("episode") or chunk.get("episode_title") or "Unknown Episode",
        guest=chunk.get("guest") or chunk.get("guest_name") or "Unknown Guest",
        timestamp=chunk.get("timestamp") or chunk.get("timestamp_ref") or "N/A",
        score=chunk.get("score") or 0.0,
        url=chunk.get("url"),
    )


@app.post("/ask", response_model=AskResponse)
async def ask(request: AskRequest, db: Session = Depends(get_db)):
    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    try:
        retriever = TranscriptRetriever(db)
        chunks = retriever.retrieve_relevant_chunks(question, top_k=5)
    except Exception:
        logger.exception("Retrieval failed")
        raise HTTPException(status_code=502, detail="Retrieval step failed. Check DB connection.")

    try:
        answer = await generate_answer(question, chunks)
    except Exception:
        logger.exception("Generation failed")
        raise HTTPException(status_code=502, detail="LLM generation failed. Check Ollama/API is running and responsive.")

    is_grounded = bool(chunks) and "do not provide enough information" not in answer

    return AskResponse(
        answer=answer,
        grounded=is_grounded,
        sources=[to_source(c) for c in chunks] if is_grounded else [],
    )