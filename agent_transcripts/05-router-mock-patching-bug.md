# Agent Transcript 05 — "Patch Where It's Used, Not Where It's Defined"

## Problem

While writing `tests/test_router_fallback.py`, an early verification script
did:

```python
import app.config
from unittest.mock import patch

with patch.object(app.config, "OPENAI_API_KEY", None):
    # ... call generate_with_fallback() and expect the no-cloud-key error path
```

The test failed: `generate_with_fallback()` still behaved as if
`OPENAI_API_KEY` were set, even though `app.config.OPENAI_API_KEY` was
definitely patched to `None`.

## Investigation

`app/llm/router.py` imports the value at module load time:

```python
from app.config import FORCE_LLM_PROVIDER, OLLAMA_BASE_URL, OLLAMA_MODEL, OPENAI_API_KEY
```

This binds a *local name* `OPENAI_API_KEY` inside the `app.llm.router`
module's namespace, copied from whatever `app.config.OPENAI_API_KEY` held at
import time. Patching `app.config.OPENAI_API_KEY` afterward changes the
attribute on the `app.config` module object, but `app.llm.router`'s own
`OPENAI_API_KEY` name is a separate reference that was already resolved at
import time — it doesn't get updated by patching the source module.

This is the classic "patch where it's used, not where it's defined" mocking
pitfall: `unittest.mock.patch` works by temporarily replacing an attribute on
a specific object. If the code under test imported a *value* (rather than
importing the *module* and doing attribute access through it), there are now
two separate names pointing at what used to be the same value, and only one
of them is reachable from `app.config`.

## Fix

Patch the name where the router module actually looks it up:

```python
with patch.object(router_mod, "OPENAI_API_KEY", None):
    ...
```

i.e. patch `app.llm.router.OPENAI_API_KEY`, not `app.config.OPENAI_API_KEY`.
This is the pattern used throughout `test_router_fallback.py` for
`OPENAI_API_KEY`, `FORCE_LLM_PROVIDER`, and `OllamaClient`.

## Lesson

Whenever a module does `from somewhere import NAME` (as opposed to `import
somewhere` + `somewhere.NAME`), mocking `somewhere.NAME` after that import
has already happened will not affect the importing module's copy of the
name. Check *where the name is looked up at call time*, not where it's
canonically defined, before writing a `patch.object(...)` call — this cost
real debugging time on a test that looked like it should obviously work.
