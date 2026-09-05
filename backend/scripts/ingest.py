import re
import sys
from pathlib import Path

import yaml

# Ensures the backend/ folder (which contains the `app` package) is importable
# regardless of how this script is invoked (e.g. `python scripts/ingest.py`
# from within backend/, which otherwise only puts scripts/ on sys.path).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.rag.embeddings import generate_embedding
from app.database import SessionLocal
from app.models.db_models import TranscriptChunk

TRANSCRIPTS_DIR = (
    Path(__file__).resolve().parents[2]
    / "lennys-podcast-transcripts"
    / "episodes"
)

FRONTMATTER_RE = re.compile(r"^---\r?\n(.*?)\r?\n---\r?\n", re.DOTALL)


def chunk_text(text: str, chunk_size: int = 3000, overlap: int = 500):
    """
    Split transcript text into overlapping chunks.

    Roughly corresponds to the company's requested
    500-800 token chunks with overlap.
    """
    chunks = []
    start = 0

    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end].strip()

        if chunk:
            chunks.append(chunk)

        start = end - overlap

    return chunks


def parse_frontmatter(raw_text: str, file_path: Path) -> dict:
    """
    Extracts the YAML frontmatter block (guest, title, youtube_url, etc.)
    that each transcript file starts with. Falls back to folder-name-based
    values if frontmatter is missing or malformed, so ingestion never hard
    fails on a single bad file.
    """
    match = FRONTMATTER_RE.match(raw_text)
    fallback_title = file_path.parent.name.replace("-", " ").title()

    if not match:
        return {"title": fallback_title, "guest": None, "url": None, "body": raw_text}

    try:
        meta = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        meta = {}

    body = raw_text[match.end():]

    return {
        "title": meta.get("title") or fallback_title,
        "guest": meta.get("guest"),
        "url": meta.get("youtube_url"),
        "body": body,
    }


def load_transcripts():
    transcripts = []

    for file_path in TRANSCRIPTS_DIR.rglob("*.md"):
        raw_text = file_path.read_text(encoding="utf-8")
        meta = parse_frontmatter(raw_text, file_path)
        transcripts.append({"file": file_path, **meta})

    return transcripts


def main():
    transcripts = load_transcripts()

    print(f"Found {len(transcripts)} transcripts.")

    session = SessionLocal()
    total_chunks = 0

    try:
        for episode_number, transcript in enumerate(transcripts, start=1):
            chunks = chunk_text(transcript["body"])

            print(
                f"[{episode_number}/{len(transcripts)}] "
                f"{transcript['title']} (guest: {transcript['guest'] or 'unknown'}) "
                f"-> {len(chunks)} chunks"
            )

            for chunk in chunks:
                embedding = generate_embedding(chunk)

                row = TranscriptChunk(
                    episode_title=transcript["title"],
                    episode_url=transcript["url"],
                    chunk_text=chunk,
                    speaker=transcript["guest"],
                    timestamp=None,
                    embedding=embedding,
                )

                session.add(row)
                total_chunks += 1

                if total_chunks % 100 == 0:
                    session.commit()
                    print(f"  Stored {total_chunks} chunks...")

        session.commit()

        print()
        print("================================")
        print("INGESTION COMPLETE")
        print("================================")
        print(f"Transcripts: {len(transcripts)}")
        print(f"Chunks stored: {total_chunks}")

    except Exception:
        session.rollback()
        raise

    finally:
        session.close()


if __name__ == "__main__":
    main()