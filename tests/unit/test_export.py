"""Tests for the printable HTML worksheet export (parent zone only)."""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from medhabhyasah.export import render_worksheet_html, slugify

_REQUEST = {"id": 1, "topic": "Electricity", "subject": "Science", "grade": "8", "exam": "CBSE"}

_Q1 = {
    "id": 10, "difficulty": "Easy", "type": "mcq",
    "question": "What is the unit of current?",
    "options": ["Volt", "Ampere", "Ohm", "Coulomb"],
    "answer": 1,
    "explanation": "Current is measured in amperes.",
    "source_quote": "", "status": "approved",
}
_Q2 = {
    "id": 11, "difficulty": "Medium", "type": "mcq",
    "question": "What is the unit of resistance?",
    "options": ["Volt", "Ampere", "Ohm", "Coulomb"],
    "answer": 2,
    "explanation": "Resistance is measured in ohms.",
    "source_quote": "", "status": "approved",
}


# ── render_worksheet_html ─────────────────────────────────────────────────────

def test_renders_all_questions_in_order():
    html = render_worksheet_html(_REQUEST, [_Q1, _Q2])
    assert html.index("unit of current") < html.index("unit of resistance")


def test_options_rendered_with_letters():
    html = render_worksheet_html(_REQUEST, [_Q1])
    assert "Ampere" in html and "Ohm" in html


def test_answer_key_has_correct_letter_and_explanation():
    html = render_worksheet_html(_REQUEST, [_Q1, _Q2])
    key_section = html[html.index("Answer Key"):]
    assert "<strong>1. B</strong>" in key_section
    assert "<strong>2. C</strong>" in key_section
    assert "measured in amperes" in key_section
    assert "measured in ohms" in key_section


def test_worksheet_does_not_reveal_answers_before_answer_key():
    html = render_worksheet_html(_REQUEST, [_Q1])
    worksheet_section = html[: html.index("Answer Key")]
    assert "Current is measured in amperes" not in worksheet_section


def test_title_includes_topic_and_subject():
    html = render_worksheet_html(_REQUEST, [_Q1])
    assert "Electricity" in html and "Science" in html


def test_print_button_present():
    html = render_worksheet_html(_REQUEST, [_Q1])
    assert "window.print()" in html


def test_csp_meta_present():
    html = render_worksheet_html(_REQUEST, [_Q1])
    assert "Content-Security-Policy" in html


def test_answer_key_page_break_for_print():
    html = render_worksheet_html(_REQUEST, [_Q1])
    assert "break-before:page" in html


# ── HTML-escaping (also exercised in tests/safety/test_export_safety.py) ─────

def test_question_text_is_escaped():
    q = dict(_Q1, question="What is 5 < 10 & true?")
    html = render_worksheet_html(_REQUEST, [q])
    assert "5 &lt; 10 &amp; true" in html
    assert "5 < 10 & true" not in html


def test_topic_text_is_escaped():
    req = dict(_REQUEST, topic="<b>Electricity</b>")
    html = render_worksheet_html(req, [_Q1])
    assert "&lt;b&gt;Electricity&lt;/b&gt;" in html
    assert "<b>Electricity</b>" not in html


# ── slugify ────────────────────────────────────────────────────────────────────

def test_slugify_basic():
    assert slugify("Electricity, Magnetic and Heating Effects") == "electricity-magnetic-and-heating-effects"


def test_slugify_empty_falls_back():
    assert slugify("") == "worksheet"


def test_slugify_truncates():
    assert len(slugify("x" * 200)) <= 60


# ── Route ────────────────────────────────────────────────────────────────────

def _kr(pin="1234"):
    kr = MagicMock()
    kr.get_password = MagicMock(side_effect=lambda s, u: pin if u == "parent-pin" else None)
    kr.set_password = MagicMock()
    return kr


_PIN = {"X-Parent-Pin": "1234"}


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "t.db"


@pytest.fixture()
def client(db_path: Path):
    from medhabhyasah.api import create_app
    with patch("medhabhyasah.credentials.keyring", _kr()):
        yield TestClient(create_app(db_path=db_path))


def _create_request_with_approved_question(client, db_path: Path) -> int:
    r = client.post(
        "/api/parent/generation-requests", headers=_PIN,
        json={"subject": "Science", "topic": "Electricity", "grade": "8",
              "exam": "CBSE", "question_count": 1},
    )
    req_id = r.json()["id"]
    import json as _json
    from medhabhyasah.db import create_question, get_connection
    conn = get_connection(db_path)
    create_question(
        conn, req_id, "Easy", "mcq", "What is the unit of current?",
        _json.dumps(["Volt", "Ampere", "Ohm", "Coulomb"]), "1",
        "Current is measured in amperes.", "", status="approved",
    )
    conn.close()
    return req_id


def test_export_requires_pin(client):
    assert client.post("/api/parent/generation-requests/1/export-html").status_code == 401


def test_export_404_for_missing_request(client):
    r = client.post("/api/parent/generation-requests/999/export-html", headers=_PIN)
    assert r.status_code == 404


def test_export_400_when_nothing_approved(client):
    r = client.post(
        "/api/parent/generation-requests", headers=_PIN,
        json={"subject": "Science", "topic": "Electricity", "grade": "8",
              "exam": "CBSE", "question_count": 1},
    )
    req_id = r.json()["id"]
    r2 = client.post(f"/api/parent/generation-requests/{req_id}/export-html", headers=_PIN)
    assert r2.status_code == 400


def test_export_writes_chosen_path_and_opens_browser(client, db_path, tmp_path):
    req_id = _create_request_with_approved_question(client, db_path)
    save_path = tmp_path / "worksheet.html"
    fake_window = MagicMock()
    fake_window.create_file_dialog.return_value = (str(save_path),)
    client.app.state.webview_window = fake_window

    with patch("medhabhyasah.api.parent.webbrowser.open") as mock_open:
        r = client.post(f"/api/parent/generation-requests/{req_id}/export-html", headers=_PIN)

    assert r.status_code == 200
    assert r.json() == {"ok": True, "cancelled": False}
    assert save_path.exists()
    assert "unit of current" in save_path.read_text(encoding="utf-8")
    mock_open.assert_called_once()


def test_export_cancelled_dialog_writes_nothing(client, db_path):
    req_id = _create_request_with_approved_question(client, db_path)
    fake_window = MagicMock()
    fake_window.create_file_dialog.return_value = None
    client.app.state.webview_window = fake_window

    with patch("medhabhyasah.api.parent.webbrowser.open") as mock_open:
        r = client.post(f"/api/parent/generation-requests/{req_id}/export-html", headers=_PIN)

    assert r.status_code == 200
    assert r.json() == {"ok": True, "cancelled": True}
    mock_open.assert_not_called()


def test_export_without_window_returns_500(client, db_path):
    req_id = _create_request_with_approved_question(client, db_path)
    client.app.state.webview_window = None
    r = client.post(f"/api/parent/generation-requests/{req_id}/export-html", headers=_PIN)
    assert r.status_code == 500
