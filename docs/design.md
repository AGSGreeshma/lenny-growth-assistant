# Design — The Lenny Growth Assistant

## Status

The chat experience described in sections 1-4 is implemented. The session
sidebar, artifact viewer, and model-toggle UI described in sections 5-6 are
planned additions, not yet built — included here as the design target so
implementation stays consistent.

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

- Semantic heading structure in `Header`/`EmptyState`.
- `.sr-only` utility present in the design system for screen-reader-only text
  (e.g. loading state announcements — to be applied to the loading indicator).
- Color contrast: ink (#1c1915) on paper (#f4efe6) and cream (#fffaf3)
  backgrounds meets WCAG AA for body text.
- Planned: `aria-live="polite"` region around the message list so screen reader
  users are notified when a new answer arrives, and visible focus states on the
  composer and submit control.