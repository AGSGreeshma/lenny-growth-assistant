import argparse
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

# Matches this corpus's dominant turn-header format, e.g.:
#   "Ada Chen Rekhi (00:00:00):"   (first line of a speaker's turn)
#   "(00:01:21):"                  (continuation of the same speaker)
#   "Lenny (00:52):"               (some shorter/clip transcripts use MM:SS)
# Anchored to a whole line (MULTILINE + $) so it does not match inline,
# mid-sentence timestamps like "[inaudible 00:00:42]".
TURN_HEADER_RE = re.compile(
    # [ \t]* (not \s*) between the speaker and the opening paren -- \s*
    # matches newlines too, which let this accidentally match a whole
    # preceding paragraph as "speaker" when that line had no literal "("
    # in it, bridging across the newline to the next line's real header.
    r"^(?P<speaker>[^\n(][^\n]*?)?[ \t]*\((?P<ts>(?:\d{1,2}:)?\d{2}:\d{2})\):[ \t]*$",
    re.MULTILINE,
)


def chunk_text(text: str, chunk_size: int = 3000, overlap: int = 500):
    """
    Split transcript text into overlapping chunks by raw character count,
    with no awareness of sentence/turn boundaries. Used as a fallback (see
    build_chunks()) for the small number of transcripts that don't use this
    corpus's dominant "Speaker (HH:MM:SS):" turn-header format.

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


def parse_turns(body: str) -> list[dict]:
    """Split a transcript body into (speaker, timestamp, raw_text) turns
    using the "Speaker (HH:MM:SS):" / "(HH:MM:SS):" header lines this
    corpus's transcripts mostly use. Returns [] if the transcript doesn't
    use this format at all (verified against the full corpus: 301/303
    files match; the other 2 use a different format entirely and fall back
    to chunk_text() instead -- see build_chunks())."""
    matches = list(TURN_HEADER_RE.finditer(body))
    if not matches:
        return []

    turns = []
    last_speaker = None
    for i, m in enumerate(matches):
        speaker = (m.group("speaker") or "").strip() or last_speaker
        last_speaker = speaker
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        # Include the header line itself in raw_text (not just what follows
        # it) so chunk content reads identically to the original transcript
        # -- this pass changes chunk *boundaries* and adds structured
        # speaker/timestamp metadata, not the visible text formatting.
        raw_text = body[m.start():end].strip()
        if raw_text:
            turns.append({"speaker": speaker, "timestamp": m.group("ts"), "raw_text": raw_text})

    return turns


def chunk_turns(turns: list[dict], chunk_size: int = 3000, overlap: int = 500) -> list[dict]:
    """Group whole turns into ~chunk_size-character chunks, never splitting
    a turn (and therefore never splitting mid-sentence the way raw
    character-based chunking can). Each chunk records the timestamp and
    speaker of its *first* turn -- a reasonable single value for a DB column
    that only stores one of each per chunk, even though a chunk spanning
    multiple turns may include more than one speaker in its text.

    Overlap is turn-based (carry the trailing turns worth ~`overlap`
    characters into the start of the next chunk) rather than a character
    slice, for the same "don't split mid-turn" reason."""
    if not turns:
        return []

    chunks = []
    n = len(turns)
    i = 0

    while i < n:
        chunk_start_idx = i
        current = []
        current_len = 0

        while i < n and current_len < chunk_size:
            current.append(turns[i])
            current_len += len(turns[i]["raw_text"])
            i += 1

        chunks.append(
            {
                "text": "\n\n".join(t["raw_text"] for t in current),
                "timestamp": current[0]["timestamp"],
                "speaker": current[0]["speaker"],
            }
        )

        if i >= n:
            break

        # Step back over trailing turns worth ~`overlap` characters so the
        # next chunk repeats some context, guaranteeing at least one turn of
        # forward progress so this can't loop forever on one huge turn.
        back_len = 0
        j = i
        while j > chunk_start_idx and back_len < overlap:
            j -= 1
            back_len += len(turns[j]["raw_text"])
        i = max(j, chunk_start_idx + 1)

    return chunks


def build_chunks(transcript: dict) -> list[dict]:
    """Returns a list of {text, timestamp, speaker} dicts for one
    transcript: turn-aware chunking (see chunk_turns()) when the transcript
    uses this corpus's dominant turn-header format, falling back to plain
    character-based chunking (with no timestamp and the episode's guest as
    a blanket speaker -- the previous behavior for every transcript) when it
    doesn't."""
    turns = parse_turns(transcript["body"])
    if turns:
        return chunk_turns(turns)

    return [
        {"text": chunk, "timestamp": None, "speaker": transcript["guest"]}
        for chunk in chunk_text(transcript["body"])
    ]


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


def already_ingested_titles(session) -> set:
    """Episode titles that already have at least one chunk stored. Used to
    skip re-embedding/re-inserting episodes ingest.py has already processed,
    so running this script again (e.g. after adding new transcript files)
    only ingests what's new instead of duplicating every existing chunk --
    there is no unique constraint on transcript_chunks, so without this
    check a second run would double every row."""
    from sqlalchemy import distinct

    rows = session.query(distinct(TranscriptChunk.episode_title)).all()
    return {row[0] for row in rows}


def main():
    parser = argparse.ArgumentParser(description="Ingest Lenny's Podcast transcripts.")
    parser.add_argument(
        "--force",
        action="store_true",
        help=(
            "Re-ingest episodes even if chunks already exist for them "
            "(deletes and replaces that episode's existing chunks first, "
            "rather than skipping it)."
        ),
    )
    args = parser.parse_args()

    transcripts = load_transcripts()

    print(f"Found {len(transcripts)} transcripts.")

    session = SessionLocal()
    total_chunks = 0
    skipped_episodes = 0
    already_ingested = already_ingested_titles(session)
    if already_ingested:
        print(
            f"{len(already_ingested)} episode(s) already have chunks stored "
            f"-- {'re-ingesting anyway (--force)' if args.force else 'skipping them'}."
        )

    try:
        for episode_number, transcript in enumerate(transcripts, start=1):
            if transcript["title"] in already_ingested:
                if not args.force:
                    skipped_episodes += 1
                    continue
                session.query(TranscriptChunk).filter(
                    TranscriptChunk.episode_title == transcript["title"]
                ).delete()

            chunks = build_chunks(transcript)

            print(
                f"[{episode_number}/{len(transcripts)}] "
                f"{transcript['title']} (guest: {transcript['guest'] or 'unknown'}) "
                f"-> {len(chunks)} chunks"
            )

            for chunk in chunks:
                embedding = generate_embedding(chunk["text"])

                row = TranscriptChunk(
                    episode_title=transcript["title"],
                    episode_url=transcript["url"],
                    chunk_text=chunk["text"],
                    speaker=chunk["speaker"],
                    timestamp=chunk["timestamp"],
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
        print(f"Transcripts found: {len(transcripts)}")
        print(f"Episodes skipped (already ingested): {skipped_episodes}")
        print(f"Chunks stored this run: {total_chunks}")

    except Exception:
        session.rollback()
        raise

    finally:
        session.close()


if __name__ == "__main__":
    main()