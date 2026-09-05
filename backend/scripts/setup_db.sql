-- Run in the Supabase SQL editor. Safe to re-run (all IF NOT EXISTS).

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "pgcrypto";  -- for gen_random_uuid()

-- Existing table (documented here for completeness / fresh environments)
CREATE TABLE IF NOT EXISTS transcript_chunks (
    id BIGSERIAL PRIMARY KEY,
    episode_title TEXT NOT NULL,
    episode_url   TEXT,
    chunk_text    TEXT NOT NULL,
    speaker       TEXT,
    timestamp     TEXT,
    embedding     VECTOR(384) NOT NULL
);

CREATE INDEX IF NOT EXISTS transcript_chunks_embedding_idx
ON transcript_chunks
USING hnsw (embedding vector_cosine_ops);

-- New: session persistence
CREATE TABLE IF NOT EXISTS sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS messages (
    id BIGSERIAL PRIMARY KEY,
    session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    sources JSONB,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS messages_session_id_idx ON messages(session_id);