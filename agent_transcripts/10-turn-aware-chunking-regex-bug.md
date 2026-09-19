# Agent Transcript 10 — A Regex That Silently Ate a Paragraph as a "Speaker Name"

## Problem

The audit flagged two related gaps: chunking split transcripts at raw
character counts (risking mid-sentence cuts) and the `timestamp` column was
never populated despite the schema supporting it. Investigating the actual
transcript files turned up real per-turn markers already present in the
source data (`Speaker (HH:MM:SS):` header lines, e.g. `Ada Chen Rekhi
(00:00:00):`), which meant both gaps could be fixed properly instead of
worked around — chunk on whole turns, and record each chunk's real
timestamp and speaker from its first turn.

A first regex to detect these headers:

```python
TURN_HEADER_RE = re.compile(
    r"^(?P<speaker>[^\n(][^\n]*?)?\s*\((?P<ts>(?:\d{1,2}:)?\d{2}:\d{2})\):[ \t]*$",
    re.MULTILINE,
)
```

A smoke test against a handful of transcripts looked mostly right, but one
chunk's `speaker` field came back as an entire paragraph of ad-read copy:
`"As of today's, Sprig is making that even easier with the new and improved
templates library. ..."` — clearly not a name.

## Investigation

Printed the raw regex matches directly. The match with `ts='00:01:21'` had
`speaker` set to the full text of *a different, preceding* sentence — not
metadata corruption, a genuine match spanning content that should never
have been in the same group.

Root cause: `\s*` between the optional speaker group and the literal `(`
matches newlines too, not just spaces. A monologue paragraph immediately
followed by a bare continuation marker on the next line —

```
We do a live exercise around my own personal values. ... short word from our sponsors.
(00:01:40):
```

— has no `(` anywhere within the paragraph's own line, so `[^\n]*?`
(non-newline, lazy) can't find a match ending in `(` *within that line*.
But `\s*` right after it doesn't stop at the line's own newline — it happily
consumes the `\n` and connects straight through to the `(00:01:40):` header
starting the very next line. The regex engine, anchored at `^` for that
paragraph's line start, found a complete match by treating the entire
paragraph as the "speaker" and the *following* line's timestamp as the
header's timestamp. `re.MULTILINE` + `$` constrained where matches could
*start* and *end*, but did nothing to stop `\s*` from bridging two lines in
the middle.

## Fix

Changed the gap between speaker and timestamp from `\s*` (any whitespace,
including newlines) to `[ \t]*` (spaces/tabs only, no newlines):

```python
r"^(?P<speaker>[^\n(][^\n]*?)?[ \t]*\((?P<ts>(?:\d{1,2}:)?\d{2}:\d{2})\):[ \t]*$"
```

Re-ran the full-corpus check after the fix: 301/303 transcripts still parse
via this format (unchanged), 62,684 turns extracted, and — the number that
actually proves the bug is gone — **zero** turns with an unresolved
(`None`) speaker, versus paragraphs-as-speaker-names before.

## Lesson

`\s` matching newlines is the correct, well-known behavior — the bug wasn't
in not knowing that, it was in not asking "which of these regex pieces
could this cost me a line boundary?" before running it. A quick smoke test
against a handful of files caught this fast specifically because it printed
*actual values*, not just counts — "5 chunks found" would have looked like
success. Whenever a regex is meant to match within a single line, prefer
`[ \t]*`/`[^\n]` explicitly over `\s`/`.` and verify against a value-level
spot check, not just a match count, before trusting it across an entire
corpus.
