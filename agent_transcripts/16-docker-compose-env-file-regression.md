# Agent Transcript 16 — A Fix for One Machine Silently Broke the Repo's Own "One-Command Startup"

## Problem

While wiring the Dockerized backend to read `DATABASE_URL` from
`backend/.env` (so this machine's Supabase connection string never had to
be hardcoded into the tracked `docker-compose.yml`), the change added
`env_file: ./backend/.env` and removed the hardcoded local-database
default entirely. This worked, was verified live, and was committed.

A later, unrelated re-audit of the repo's deliverables ("do one last
check") asked specifically whether the documented "Option A: Docker
Compose (recommended)" one-command path still worked — prompting an actual
test rather than an assumption that a previously-verified change was still
fine.

## Investigation

`backend/.env` is gitignored — it is never committed, so it does not exist
on a fresh clone. Tested directly rather than reasoned about abstractly:
temporarily moved `backend/.env` aside and ran `docker compose config`.
Result:

```
env file .../backend/.env not found
```

Docker Compose treats a required `env_file` that doesn't exist as a
compose-level configuration error — it fails before the application layer
ever runs, not as a graceful "DATABASE_URL missing" app error. Since there
was no longer any `DATABASE_URL` default in the `environment:` block
either, a fresh clone following the README's own "Option A" instructions
literally could not run `docker compose up --build` at all.

## Fix

Restored `DATABASE_URL: ${DATABASE_URL:-postgresql://postgres:postgres@db:5432/lenny}`
in the `environment:` block (the same override-with-a-safe-default pattern
every other variable in that block already uses) and removed the hard
`env_file:` requirement entirely. This machine's own Supabase override now
comes from the project root's `.env` (which Docker Compose auto-loads for
variable substitution when it sits next to the compose file) rather than a
required `env_file:` directive — while investigating this, found that the
root `.env`'s own `DATABASE_URL` was itself still the broken IPv6-only
Direct Connection string from Transcript 14, not the working Session
Pooler one — corrected it to match `backend/.env`'s verified-working value
at the same time.

Verified both directions empirically, not assumed from the config alone:
- Moved *both* `.env` files aside (a true fresh-clone simulation) and
  confirmed `docker compose config` now resolves `DATABASE_URL` to the
  local `db` service default with no error.
- Restored both files and confirmed `docker compose up -d backend` still
  resolves to the Supabase pooler host, and `/api/health` still reports
  `db: ok` against it.

## Lesson

A change verified correct for the one machine it was tested on can still
be a regression for everyone else, if that machine's own local state
(a file that happens to already exist there) is quietly doing the work of
making the change look complete. The fix that mattered here wasn't found
by re-reading the diff — it was found by asking "would this work on a
machine that doesn't already have my files on it," and then actually
removing those files to check, rather than trusting that a working
`docker compose up` on this machine meant the repository itself was still
correct.
