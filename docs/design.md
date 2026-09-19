# Design — The Lenny Growth Assistant

## Status

The chat experience described in sections 1-4 is implemented, including the
not-grounded visual state. The artifact viewer (section 6) and a
provider-toggle control (in the header, not a separate model-toggle UI as
originally sketched) are also implemented. The session sidebar (section 5)
remains a planned addition, not yet built.

## 1. UI/UX Principles

- **Editorial, not generic-chatbot.** The palette (warm paper background,
  deep moss green accent, Fraunces serif for display text paired with Outfit
  sans-serif for UI) is deliberately closer to a well-typeset publication than
  a default chat template — this is a *knowledge product*, not a toy chatbot,
  and the visual language should signal that.
- **Sources are first-class, not a footnote.** Every grounded answer surfaces
  its transcript sources as visible cards (episode, speaker, similarity score),
  not a collapsed "show sources" link — trust in a RAG product depends on the
  user being able to verify claims at a glance.
- **Honest about uncertainty.** When the assistant can't ground an answer, the
  UI should present that as a distinct, calmly-styled state — not the same
  visual treatment as a confident answer.

## 2. Information Architecture

```
App
 └─ Header (product name/branding)
 └─ Chat
     ├─ EmptyState (shown before first question — example prompts)
     ├─ ChatMessage[] (user + assistant turns)
     │    └─ AnswerContent (renders assistant markdown)
     │    └─ SourceCard[] (per-answer citations)
     └─ QuestionInput (composer, submit on enter)
```

## 3. Key Interaction States

- **Empty state:** shown before any question is asked; surfaces example prompts
  so a new user isn't staring at a blank box.
- **Loading state:** a placeholder assistant message with a loading indicator is
  inserted immediately on submit, so the UI never feels frozen during the
  (sometimes 30-60s) local-model generation time.
- **Success state:** answer renders with its source cards.
- **Error state:** distinct, friendly copy per failure mode (network unreachable,
  4xx validation, 5xx generation failure) rather than a raw error dump — see
  `services/api.js`'s `friendlyHttpError`.
- **Not-grounded state (planned refinement):** when `grounded: false` comes back
  from the API, the UI should visually distinguish "I don't know" from a normal
  answer (e.g. muted styling, no source cards) rather than rendering it identically
  to a confident response.

## 4. Responsive Behavior

Single-column chat layout using `h-dvh` (dynamic viewport height) so it behaves
correctly on mobile browsers where the address bar changes visible height.
Composer is pinned to the bottom of the viewport; message list scrolls
independently.

## 5. Planned: Session Sidebar

A collapsible left sidebar listing past sessions (title = first question,
timestamp), with a "New chat" action. Selecting a session loads its message
history via `GET /api/sessions/{id}` and continues the conversation with full
prior context.

## 6. Planned: Artifact Viewer

A collapsible right-hand pane, mirroring the Claude Artifacts pattern:
- Triggered when a response includes a generated Markdown/HTML artifact (e.g.
  a Ship 30 for 30 essay).
- Markdown renders via `react-markdown`; HTML renders inside a sandboxed
  `<iframe>` (see architecture.md for the security model).
- A visible badge indicates artifact type and a "Sandboxed" label, so the user
  understands the trust boundary rather than assuming full-page access.
- Collapses on narrow viewports to a full-screen overlay rather than a
  fixed side-by-side pane, to preserve usability on mobile.

## 7. Accessibility

- **Heading structure:** a single `<h1>` (`Header`, always present, not
  conditional on chat state) with `<h2>`s below it (`EmptyState`'s tagline,
  each message's "Sources" section) — screen reader users navigating by
  heading get a real page outline at every state, not just on first load.
- **Live regions:** the message list uses `role="log"` + `aria-live="polite"`
  (`Chat.jsx`) so new messages are announced without re-reading the whole
  transcript; the loading indicator uses `role="status"`; error states use
  `role="alert"`.
- **Focus visibility:** every interactive control (buttons, links, the
  composer) has an explicit `focus-visible:ring-2` style — verified this
  isn't left to browser defaults on any control, including ones added after
  the initial pass (provider toggle, "New chat", "Turn into essay",
  artifact viewer's "Close", the init-error "Retry" button).
- **Artifact viewer:** rendered as an `<aside aria-label="Generated
  artifact">` landmark, closeable via a focus-visible "Close" button or the
  Escape key.
- **Labels & names:** the composer's textarea has a real (`.sr-only`)
  `<label>`, not just a placeholder, and is `aria-describedby`-linked to the
  "Enter to send" hint; source links that open in a new tab say so via
  `.sr-only` text, not just visually.
- **Color contrast:** ink (#1c1915) on paper (#f4efe6) and cream (#fffaf3)
  backgrounds meets WCAG AA for body text; the not-grounded (amber) and
  error (rose) states use sufficiently dark text on their tinted
  backgrounds.
- **Not yet done:** no automated accessibility test (e.g. axe) in the test
  suite; keyboard-only navigation and screen-reader behavior verified by
  code inspection and a rendered-DOM check, not a full manual screen-reader
  pass.