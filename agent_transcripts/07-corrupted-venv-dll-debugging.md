# Agent Transcript 07 — Corrupted Windows venv: numpy/torch "DLL load failed"

## Problem

Picking up the handoff from a prior session, the first step was to actually
run the existing pytest suite (it had only been verified ad hoc via
throwaway scripts before, since that session had no local shell access).
`pip install -r requirements-dev.txt` succeeded cleanly, but running the new
retriever tests failed at collection with:

```
ImportError: ... Importing the numpy C-extensions failed ...
Original error was: DLL load failed while importing _multiarray_umath:
The specified module could not be found.
```

A bare `python -c "import numpy"` reproduced the same failure outside pytest
entirely — this was an environment problem, not a test-writing problem.

## Investigation

First hypothesis: the project lives under `OneDrive\Desktop\...`, and the
`.pyd` files in `site-packages/numpy` showed a `ReparsePoint` attribute —
consistent with OneDrive's Files-On-Demand turning large binary files into
cloud-only placeholders that never actually reach disk until opened. Tried
force-hydrating with `attrib +P` and by explicitly reading the file's full
byte contents (`[System.IO.File]::ReadAllBytes(...)`), which succeeded and
returned the full file size — so the files *were* actually present on disk.
The `ReparsePoint` attribute was a red herring (OneDrive can keep that flag
on fully-hydrated "always keep on this device" files too); the real problem
was something else.

Second hypothesis, confirmed: `pip install --force-reinstall --no-cache-dir
numpy` fixed the numpy import immediately. That strongly suggests the
*original* install (done in a prior, unrelated session, possibly interrupted
by a sync conflict, an antivirus lock, or a network hiccup during download)
had left a subtly corrupted wheel extraction on disk — one where file sizes
looked plausible but a `.pyd`'s actual dependency chain was broken. Loading
`app.rag.embeddings` next surfaced the identical failure pattern one layer
deeper, in `torch/lib/shm.dll`, and then again in `scipy/linalg/_fblas` after
reinstalling torch — three separate packages in the same venv, all showing
the same "file exists, but DLL load fails" signature.

## Fix

Rather than keep reinstalling packages one at a time as each new import path
surfaced another corrupted one, deleted the entire `venv/` directory and
recreated it from scratch (`python -m venv venv`), then did a single clean
`pip install --no-cache-dir -r requirements.txt -r requirements-dev.txt` into
the fresh environment. This is slower than patching individual packages but
correct: it doesn't rely on having already discovered every corrupted
package via a failing import.

## Lesson

"DLL load failed: the specified module could not be found" on Windows, even
when the file in question demonstrably exists and reads back the right byte
count, is more often a sign of **install-time corruption of a binary
dependency chain** than a genuinely missing file. Don't spend time
hydration-debugging or DLL-dependency-walking before trying the cheap fix
first (`--force-reinstall --no-cache-dir`), and once two unrelated packages
in the same venv show the identical symptom, stop patching individually and
recreate the environment — the corruption is almost certainly systemic to
that install, not specific to any one package.
