# Agent Transcript 14 — Supabase Connection: Wrong File, Then Wrong Connection Type

## Problem

Migrating the database target from local Docker Postgres to a newly-created
Supabase project. After pointing `backend/.env`'s `DATABASE_URL` at
Supabase and testing with a plain `psycopg.connect(...)` script, the
connection failed identically every time:

```
FATAL: (ENOTFOUND) tenant/user postgres.<project-ref> not found
```

The user had already gone to Supabase → Connect → Direct connection → URI
and updated ".env" — but the error persisted unchanged, showing a pooler
hostname (`aws-0-...pooler.supabase.com`) instead of the direct-connection
host they'd just copied.

## Investigation

Read the actual files rather than assuming. Two separate issues, found in
order:

1. **Two different `.env` files existed** (project root `.env` and
   `backend/.env`), each with a *different* `DATABASE_URL`, pointing at
   what turned out to be two *different* Supabase project refs. Verified
   empirically which one actually gets loaded: `find_dotenv()` (called
   with no arguments in `config.py`) resolves based on **current working
   directory**, not the app's own location. Tested directly — running from
   `backend/` resolves to `backend/.env`; running from the repo root
   resolves to the root `.env`. Since every documented way this project
   runs (`uvicorn` from `backend/`, `ingest.py` from `backend/`, and the
   user's own manual test) has its CWD in `backend/`, `backend/.env` is
   the one that actually loads — and it still had the *old* pooler string
   from an earlier, apparently-abandoned project ref. The user's edit had
   gone into the root `.env` instead.
2. **The Direct Connection URI itself doesn't work in this environment
   at all**, independent of which file it's in. Tested the root `.env`'s
   candidate host directly: `db.<project-ref>.supabase.co` resolved via
   DNS to an **IPv6 address only** (confirmed with `Resolve-DnsName -Type
   AAAA` returning a real record, `-Type A` returning nothing). Supabase's
   Direct Connection is IPv6-only unless a project has the paid IPv4
   add-on. Docker Desktop's default network (and this machine generally)
   has no outbound IPv6 route — confirmed via a live connection attempt
   failing with "could not translate host name." The pooler exists
   specifically as Supabase's IPv4-compatible path for exactly this
   reason.

## Fix

Got the Session Pooler URI (port `5432`, not the `6543` transaction-mode
port — session mode is needed for `ensure_schema()`'s DDL) for the
*correct*, currently-active project ref, and put it in `backend/.env`
specifically (confirmed as the file that's actually loaded). Verified
read-only before touching anything else: connectivity, the `vector`
extension, all three tables, and the `embedding vector(384)` column
definition with its HNSW index already in place from the manually-run
schema SQL.

## Lesson

Two different failure modes can look identical from the error message
alone ("wrong file" and "wrong connection type" both eventually surface as
a rejected connection), and fixing only one while assuming it's the whole
problem wastes a retry cycle. The `find_dotenv()` CWD-dependent resolution
is also a repeat of a lesson from earlier in this project (see Transcript
05's "patch where it's used, not where it's defined") in a new shape: code
that resolves configuration implicitly, based on where it happens to be
invoked from, is a recurring source of "I already fixed that" confusion.
