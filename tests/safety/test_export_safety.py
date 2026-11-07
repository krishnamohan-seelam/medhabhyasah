"""Safety: AI-authored text in the printable export must never become live HTML.

The exported file is opened directly in a real browser, outside the app's own
CSP-protected pages and textContent rendering, so every field must be escaped.
"""
from medhabhyasah.export import render_worksheet_html

_REQUEST = {"id": 1, "topic": "Electricity", "subject": "Science", "grade": "8", "exam": "CBSE"}

_MALICIOUS_PAYLOADS = [
    "<script>alert('x')</script>",
    "<img src=x onerror=alert(1)>",
    "<a href=javascript:alert(1)>click</a>",
]


def _question(**overrides):
    q = {
        "id": 1, "difficulty": "Easy", "type": "mcq",
        "question": "Safe question text",
        "options": ["A", "B", "C", "D"],
        "answer": 0,
        "explanation": "Safe explanation",
        "source_quote": "", "status": "approved",
    }
    q.update(overrides)
    return q


def _assert_inert(html: str) -> None:
    """The payload must survive only as escaped text, never as live markup."""
    assert "<script>" not in html
    assert "<img" not in html
    assert "<a href=javascript" not in html
    # Proof the text made it through (escaped), rather than being silently dropped.
    assert "alert(1)" in html or "alert(&#x27;x&#x27;)" in html


def test_script_tag_in_question_text_is_inert():
    for payload in _MALICIOUS_PAYLOADS:
        html = render_worksheet_html(_REQUEST, [_question(question=payload)])
        _assert_inert(html)


def test_script_tag_in_options_is_inert():
    for payload in _MALICIOUS_PAYLOADS:
        html = render_worksheet_html(_REQUEST, [_question(options=[payload, "B", "C", "D"])])
        _assert_inert(html)


def test_script_tag_in_explanation_is_inert():
    for payload in _MALICIOUS_PAYLOADS:
        html = render_worksheet_html(_REQUEST, [_question(explanation=payload)])
        _assert_inert(html)


def test_script_tag_in_topic_or_subject_is_inert():
    for payload in _MALICIOUS_PAYLOADS:
        req = dict(_REQUEST, topic=payload, subject=payload)
        html = render_worksheet_html(req, [_question()])
        _assert_inert(html)


def test_csp_meta_tag_present_in_export():
    html = render_worksheet_html(_REQUEST, [_question()])
    assert 'http-equiv="Content-Security-Policy"' in html
    assert "object-src 'none'" in html
