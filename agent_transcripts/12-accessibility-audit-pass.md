# Agent Transcript 12 — Accessibility Pass: the App Had No `<h1>` Once a Conversation Started

## Problem

`docs/design.md` had flagged several accessibility items as "planned"
(focus states, the message-list live region) from early in the build. One
had already been fixed earlier this session (the live region). Revisiting
the rest meant actually reading every interactive component, not trusting
the "looks done" assumption.

## Investigation

Read all 8 frontend components end to end and checked each interactive
element against three things: a real accessible name, a visible focus
state, and correct semantics. Found:

- **`Header.jsx`** rendered the product name ("Lenny Growth Assistant") as
  a `<p>`, not a heading. `EmptyState.jsx` had the only `<h1>` on the page —
  but `EmptyState` only renders before the first message. The practical
  effect: a screen reader user navigating by heading gets a page outline
  on first load, and **zero headings at all** once a conversation starts,
  including past the "Sources" `<h2>` in every answer, which then has no
  parent heading.
- **Five interactive elements with no visible focus state at all**: the
  provider-toggle buttons, "New chat", "Turn into essay", the artifact
  viewer's "Close" button, and the error banner's "Retry" button. Every one
  of these sat right next to sibling controls (the composer's submit
  button, `EmptyState`'s example buttons, `SourceCard`'s links) that
  *did* have `focus-visible:ring-2` -- an inconsistency against the app's
  own established pattern, not a missing pattern.
- The artifact viewer had no landmark role/label and no keyboard way to
  close it besides clicking (no Escape handler).
- Source links that `target="_blank"` gave no indication they open a new
  tab.

## Fix

- Made `Header`'s title a real `<h1>` (always present, not conditional),
  and demoted `EmptyState`'s tagline to `<h2>` — now there's one h1 at
  every app state, with `<h2>`s correctly nested under it.
- Added the same `focus-visible:ring-2` treatment already used elsewhere to
  all five previously-unstyled controls.
- Wrapped the artifact viewer in `<aside aria-label="Generated artifact">`
  and added an Escape-key handler to close it.
- Added `.sr-only` "(opens in a new tab)" text to source links, and
  `aria-describedby` linking the composer to its keyboard-shortcut hint.
- Gave the message list `role="log"` (the ARIA pattern for chat/transcript
  content) alongside the existing `aria-live="polite"`.

Verified via a headless-Chrome DOM dump (confirmed the `<h1>` renders at
every state, no console errors) and rebuilt/redeployed the running Docker
frontend with the fix.

## Lesson

"Focus-visible ring added to the buttons" from an earlier session pass
described what was done, not what was verified across *every* interactive
element added since. New controls (the provider toggle, artifact viewer)
were built without carrying the pattern forward automatically -- checking
against an established convention needs an explicit pass over the current
component set, not an assumption that a pattern set once stays applied.
