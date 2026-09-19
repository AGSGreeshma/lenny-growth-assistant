# Manual Test Plan — The Lenny Growth Assistant

A short, walk-through test plan for the UI, covering what the automated
backend suite (`backend/tests/`) doesn't: what a real user actually sees and
clicks. Run this against `http://localhost:5173` with the backend and
Ollama both up (see README's "Option A: Docker Compose" or "Option B:
Manual setup").

## 1. Core grounded chat

| # | Steps | Expected result |
|---|---|---|
| 1.1 | Open the app fresh (no prior session). | Empty state renders: tagline, 4 example-question cards. No chat bubbles. |
| 1.2 | Click one of the example-question cards. | The question is submitted immediately (no need to also press Enter); a loading bubble ("Searching Lenny's Podcast...") appears. |
| 1.3 | Wait for the response (can take 30s+ on CPU-only Ollama). | An "Answer" card renders with body text, a provider badge ("Local (Ollama)" or "Cloud (OpenAI)"), and a "Sources" section listing 1+ episode cards (episode name, % match, timestamp badge if available). |
| 1.4 | Click a source card's episode link. | Opens the source YouTube URL in a new tab, deep-linked to the cited timestamp when one exists. |
| 1.5 | Type a genuinely off-topic question (e.g. "What's a good pasta recipe?") and submit. | Card renders in the **amber "Not grounded"** style (not the same styling as a confident answer), with no Sources section, and no fabricated episode citation. |
| 1.6 | Ask a follow-up question that only makes sense given the previous answer (e.g. "what about for a B2B company specifically?"). | The answer reflects the prior turn's context — not treated as a fresh, context-free question. |

## 2. Ship 30 for 30 essay

| # | Steps | Expected result |
|---|---|---|
| 2.1 | On a grounded (non-"not grounded") answer, click **"Turn into essay."** | Button shows "Writing essay..." while loading; a right-hand Artifact panel opens once done. |
| 2.2 | Inspect the artifact panel. | Title reads "Ship 30 for 30: <topic>" or similar; badge shows "Markdown" (not "Sandboxed HTML"); a provider badge is present. Content shows Markdown formatting (headings, bold anchors, bullets) — not raw unrendered `**bold**`/`#` syntax. |
| 2.3 | Read the essay for length and completeness. | Should read as complete (ends on a full sentence, has a concluding checklist/framework) even if shorter than the ~1,250-word ideal — this is expected local-model behavior (see architecture.md), not a bug. It should **not** end mid-sentence or mid-word. |
| 2.4 | Close the artifact panel (Close button, or Escape key). | Panel closes; chat returns to full width. |

## 3. HTML artifact

| # | Steps | Expected result |
|---|---|---|
| 3.1 | In the chat input, type a request like "give me this as a landing page" or "turn this into an HTML one-pager" after a grounded answer. | Assistant reply is a short confirmation ("Here's your HTML artifact..."); artifact panel opens. |
| 3.2 | Inspect the artifact panel. | Badge shows **"Sandboxed HTML"**. Content renders as a styled page inside an iframe, not raw HTML source text. |
| 3.3 | Open browser dev tools and inspect the iframe element. | `sandbox="allow-scripts"` is present; no `allow-same-origin`. |
| 3.4 | Attempt to use the artifact's own interactive elements (if any) that would try to read `document.cookie` or access the parent window. | Should fail silently / have no effect — the iframe cannot reach the parent page's cookies or storage. |

## 4. Provider toggle

| # | Steps | Expected result |
|---|---|---|
| 4.1 | In the header, confirm the toggle shows **Auto / Ollama / OpenAI**, with one visibly active. | Default is "Auto." |
| 4.2 | Click "Ollama" explicitly, then ask a question. | Response's provider badge reads "Local (Ollama)." If Ollama is down, the request should fail with a clear error (not silently succeed via OpenAI) — explicitly-requested-provider does not fall back. |
| 4.3 | Click "OpenAI" explicitly (only if a funded key is configured), then ask a question. | Response's provider badge reads "Cloud (OpenAI)." |
| 4.4 | Switch back to "Auto." | Subsequent requests use Ollama first, falling back to OpenAI only if Ollama fails. |

## 5. Sessions

| # | Steps | Expected result |
|---|---|---|
| 5.1 | Have an active conversation, then click **"New chat."** | Chat area clears back to the empty state; a new session is created (new session_id). |
| 5.2 | Ask a question in this new session. | No memory of the previous session's conversation leaks in (independent context). |

## 6. Error handling

| # | Steps | Expected result |
|---|---|---|
| 6.1 | Stop the backend (or block its port), then reload the frontend and ask a question. | A clear, friendly network-error message appears — not a blank screen, not a raw browser fetch error dump. |
| 6.2 | Stop Ollama (`ollama` process not running) with no `OPENAI_API_KEY` configured, then ask a question. | Request fails with an actionable message surfaced in the UI (not a raw 500/stack trace) — see README's "What happens if Ollama is down?" |
| 6.3 | Submit an empty message (if the input allows it) or a request with an empty topic via the essay/artifact flow. | Rejected with a clear validation message, not a server error. |

## 7. Accessibility (keyboard + screen reader spot-check)

| # | Steps | Expected result |
|---|---|---|
| 7.1 | Tab through the page from the top using only the keyboard. | Every interactive control (provider toggle options, "New chat," composer, "Turn into essay," artifact "Close") receives a visible focus ring — nothing is skipped or invisible. |
| 7.2 | With the artifact panel open, press Escape. | Panel closes without needing the mouse. |
| 7.3 | Use a screen reader (or browser dev tools' accessibility tree) to check heading structure. | Exactly one `<h1>` at any given time; `<h2>`s below it for section headings (e.g. "Sources"). |
| 7.4 | Submit a question and listen with a screen reader active (or watch the ARIA live region in dev tools). | The new message is announced without the whole conversation being re-read from the top. |

## 8. Responsive layout

| # | Steps | Expected result |
|---|---|---|
| 8.1 | Resize the browser to a narrow (mobile-width) viewport with no artifact open. | Single-column chat layout remains usable; composer stays pinned to the bottom. |
| 8.2 | At the same narrow width, open an artifact (essay or HTML). | **Known gap, not yet verified/fixed** (see design.md §6): the artifact panel has no dedicated mobile overlay treatment and may crowd the chat column rather than cleanly overlaying it. Record actual behavior here if you run this. |

---

**Scope note:** this plan spot-checks the primary flows an evaluator is
likely to exercise; it isn't an exhaustive UI regression suite. Automated
coverage for backend logic (retrieval, routing, persistence, sanitization,
the timeout/soft-deadline behavior) lives in `backend/tests/` instead.
