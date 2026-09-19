import logging
import os

import httpx
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import OLLAMA_BASE_URL
from app.database import get_db, ensure_schema
from app.api import artifact, sessions, chat, essay

ensure_schema()

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

app.include_router(sessions.router)
app.include_router(chat.router)
app.include_router(essay.router)
app.include_router(artifact.router)


@app.get("/")
def root():
    return {"message": "Lenny Growth Assistant API is running!"}


def _check_db() -> tuple[str, str | None]:
    try:
        db_gen = get_db()
        db: Session = next(db_gen)
        try:
            db.execute(text("SELECT 1"))
            return "ok", None
        finally:
            db_gen.close()
    except Exception as exc:  # noqa: BLE001
        logger.exception("Health check: DB error")
        return "unavailable", str(exc)


def _check_ollama() -> tuple[str, str | None]:
    try:
        response = httpx.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=2.0)
        response.raise_for_status()
        return "ok", None
    except Exception as exc:  # noqa: BLE001
        # Not fatal: the router falls back to OpenAI if OPENAI_API_KEY is
        # configured, so Ollama being down is "degraded", not "unavailable",
        # unless the caller has no cloud fallback configured either.
        return "unreachable", str(exc)


def _check_embedding_model() -> tuple[str, str | None]:
    try:
        from app.rag.embeddings import model  # noqa: F401 - import triggers load if not already

        return ("ok", None) if model is not None else ("unavailable", "model object is None")
    except Exception as exc:  # noqa: BLE001
        return "unavailable", str(exc)


@app.get("/api/health")
def health():
    """Reports API/DB/Ollama/embedding-model status individually, plus an
    overall rollup that distinguishes "fully healthy" from "degraded but
    usable" (e.g. Ollama down but OpenAI configured) from "unavailable"
    (nothing can generate an answer at all). See docs/architecture.md's
    Observability section for how each state is used."""
    from app.config import OPENAI_API_KEY

    db_status, db_error = _check_db()
    ollama_status, ollama_error = _check_ollama()
    embedding_status, embedding_error = _check_embedding_model()

    can_generate = ollama_status == "ok" or bool(OPENAI_API_KEY)

    if db_status == "ok" and ollama_status == "ok" and embedding_status == "ok":
        overall = "healthy"
    elif db_status != "ok" or embedding_status != "ok" or not can_generate:
        overall = "unavailable"
    else:
        overall = "degraded"

    return {
        "status": overall,
        "api": "ok",
        "db": {"status": db_status, "error": db_error},
        "ollama": {"status": ollama_status, "error": ollama_error, "base_url": OLLAMA_BASE_URL},
        "embedding_model": {"status": embedding_status, "error": embedding_error},
        "cloud_fallback_configured": bool(OPENAI_API_KEY),
    }
