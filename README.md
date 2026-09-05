# The Lenny Growth Assistant

A RAG-powered assistant that answers product and growth questions using grounded,
cited answers pulled from 300+ real Lenny's Podcast transcripts.

> **Status:** Core RAG pipeline, session persistence, and the React frontend
> are implemented and working. The application supports transcript ingestion,
> pgvector retrieval, grounded Ollama answers, persistent chat sessions,
> follow-up conversation history, health checks, error handling, and
> local frontend/backend communication.
>
> The Ship 30 for 30 skill, artifact viewer, cloud-provider fallback,
> model toggle, automated pytest suite, Docker Compose deployment, and
> demo video are still in progress.

---

## Architecture Overview

See [`docs/architecture.md`](docs/architecture.md) for the full architecture
and implementation details.

Short version:

```text
React / Vite Frontend
        |
        v
FastAPI Backend
        |
        +--------------------+
        |                    |
        v                    v
Session API             Chat API
                             |
                             v
                    Transcript Retriever
                             |
                             v
                    Supabase PostgreSQL
                       + pgvector
                             |
                             v
                    Grounded LLM Generation
                             |
                             v
                         Ollama