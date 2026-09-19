"""
HTML/CSS artifact skill: turns grounded transcript material into a
self-contained, single-file HTML+CSS artifact for the in-app Artifact Viewer.

This is a dedicated skill (its own system prompt, its own generation
function, its own sanitization pass), not a branch inside the normal chat
handler -- see the assignment's 4.3 and the security expectation attached to
it. The generated HTML is treated as UNTRUSTED at every later step: the
frontend renders it in a sandboxed iframe with scripting isolated from the
parent page (``sandbox="allow-scripts"``, `allow-same-origin` deliberately
omitted -- see docs/architecture.md), and this module additionally strips the
highest-risk constructs (``<script>`` tags, inline event handlers,
``javascript:`` URLs) as a defense-in-depth measure before the HTML is ever
stored or sent to the frontend. Neither layer alone is described as making
the content "safe" in an absolute sense -- see architecture.md's security
section for the actual boundary this provides.
"""

import re

from app.llm.router import generate_with_fallback

HTML_ARTIFACT_SYSTEM_PROMPT = """You are a content designer who turns grounded \
product/growth research into a single, self-contained HTML page.

Structural requirements:
1. Output ONLY a complete HTML document: <!DOCTYPE html>...<html>...</html>. \
No Markdown, no commentary before or after, no code fences.
2. All styling must be inline in a single <style> tag in <head>. Do not \
reference any external stylesheet, font, image, or script.
3. Do NOT include any <script> tags, inline event handler attributes \
(onclick, onload, etc.), or javascript: URLs. The page must be static \
markup and CSS only.
4. Do NOT load any external resources (no <img src="http...">, no \
<link href="http...">, no <iframe>, no fetch/XHR of any kind).
5. Ground every claim strictly in the provided transcript context. Attribute \
specific points to the guest/episode they came from wherever possible. If the \
context is thin, keep the page short and honest rather than inventing detail.
6. Keep it visually clean: a clear heading, short readable sections, and -- \
where relevant -- a compact list of sourced takeaways at the end.

Do not invent facts or attribute ideas to guests who did not say them."""


def build_context(retrieved_chunks: list[dict]) -> str:
    parts = []
    for i, chunk in enumerate(retrieved_chunks, start=1):
        parts.append(
            f"""--- SOURCE {i} ---
Episode: {chunk.get("episode", "Unknown")}
Guest: {chunk.get("speaker") or chunk.get("guest") or "Unknown"}

{chunk.get("text", "")[:2500]}"""
        )
    return "\n\n".join(parts)


_SCRIPT_TAG_RE = re.compile(r"<script\b[^>]*>.*?</script>", re.IGNORECASE | re.DOTALL)
_SCRIPT_SELF_CLOSE_RE = re.compile(r"<script\b[^>]*/>", re.IGNORECASE)
_EVENT_HANDLER_ATTR_RE = re.compile(
    r'\s+on[a-z]+\s*=\s*(".*?"|\'.*?\'|[^\s>]+)', re.IGNORECASE
)
_JAVASCRIPT_URL_RE = re.compile(r'(href|src)\s*=\s*(["\'])\s*javascript:.*?\2', re.IGNORECASE)
_CODE_FENCE_RE = re.compile(r"^```(?:html)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)


def sanitize_html(raw_html: str) -> str:
    """Best-effort, dependency-free stripping of the highest-risk HTML
    constructs. This is a defense-in-depth measure, NOT the primary security
    boundary -- the primary boundary is the sandboxed iframe the frontend
    renders this content in (no `allow-same-origin`, so even HTML that slips
    past this pass cannot read the parent page's cookies/storage or escape
    the iframe). See docs/architecture.md for the full threat model."""
    html = _CODE_FENCE_RE.sub("", raw_html.strip())
    html = _SCRIPT_TAG_RE.sub("", html)
    html = _SCRIPT_SELF_CLOSE_RE.sub("", html)
    html = _EVENT_HANDLER_ATTR_RE.sub("", html)
    html = _JAVASCRIPT_URL_RE.sub(lambda m: f'{m.group(1)}="#"', html)
    return html.strip()


async def generate_html_artifact(
    topic: str, retrieved_chunks: list[dict], force_provider: str | None = None
) -> tuple[str, str]:
    """Returns (sanitized_html, provider). Raises RuntimeError if generation
    fails, same failure mode as the other generation paths."""
    context = build_context(retrieved_chunks)

    user_prompt = f"""Topic to build the HTML artifact around:
{topic}

Retrieved podcast context:
{context}

Produce the complete, self-contained HTML page now, following all structural
requirements."""

    raw_html, provider = await generate_with_fallback(
        messages=[{"role": "user", "content": user_prompt}],
        system_prompt=HTML_ARTIFACT_SYSTEM_PROMPT,
        force_provider=force_provider,
    )
    return sanitize_html(raw_html), provider
