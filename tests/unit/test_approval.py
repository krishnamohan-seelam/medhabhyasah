"""Tests for question approval queue — status transitions and API routes."""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


def _make_db(tmp_path: Path):
    from medhabhyasah.api import create_app
    app = create_app(db_path=tmp_path / "test.db")
    return app, TestClient(app)


def _pin_mock(pin="1234"):
    mock = MagicMock()
    mock.get_password = MagicMock(return_value=pin)
    mock.set_password = MagicMock()
    return mock


_VALID_Q = {
    "difficulty": "Easy",
    "type": "mcq",
    "question": "What is 2 + 2?",
    "options": ["1", "2", "4", "5"],
    "answer": 2,
    "explanation": "2+2=4",
    "source_quote": "",
}


def _seed_question(tmp_path, status="auto_checked"):
    """Create a generation request + one question; return (client, req_id, q_id)."""
    from medhabhyasah.db import (
        create_generation_request, create_question, create_schema, get_connection
    )
    conn = get_connection(tmp_path / "test.db")
    create_schema(conn)
    req_id = create_generation_request(
        conn, subject="Maths", topic="Algebra", grade="9",
        exam="CBSE", references_text="", question_count=1,
    )
    q_id = create_question(
        conn,
        generation_request_id=req_id,
        difficulty=_VALID_Q["difficulty"],
        type_=_VALID_Q["type"],
        question=_VALID_Q["question"],
        options=json.dumps(_VALID_Q["options"]),
        answer=str(_VALID_Q["answer"]),
        explanation=_VALID_Q["explanation"],
        source_quote=_VALID_Q["source_quote"],
        status=status,
    )
    conn.close()

    from medhabhyasah.api import create_app
    app = create_app(db_path=tmp_path / "test.db")
    return TestClient(app), req_id, q_id


# ── Status transition tests ───────────────────────────────────────────────────

@pytest.mark.parametrize("initial", ["draft", "auto_checked"])
def test_approve_question_sets_approved(tmp_path, initial):
    with patch("medhabhyasah.credentials.keyring", _pin_mock()):
        c, req_id, q_id = _seed_question(tmp_path, status=initial)
        r = c.post(f"/api/parent/questions/{q_id}/approve",
                   headers={"X-Parent-Pin": "1234"})
    assert r.status_code == 200
    assert r.json()["status"] == "approved"


@pytest.mark.parametrize("initial", ["draft", "auto_checked"])
def test_reject_question_sets_rejected(tmp_path, initial):
    with patch("medhabhyasah.credentials.keyring", _pin_mock()):
        c, req_id, q_id = _seed_question(tmp_path, status=initial)
        r = c.post(f"/api/parent/questions/{q_id}/reject",
                   headers={"X-Parent-Pin": "1234"})
    assert r.status_code == 200
    assert r.json()["status"] == "rejected"


def test_undo_approved_reverts_to_auto_checked(tmp_path):
    with patch("medhabhyasah.credentials.keyring", _pin_mock()):
        c, req_id, q_id = _seed_question(tmp_path, status="auto_checked")
        c.post(f"/api/parent/questions/{q_id}/approve",
               headers={"X-Parent-Pin": "1234"})
        r = c.post(f"/api/parent/questions/{q_id}/undo",
                   headers={"X-Parent-Pin": "1234"})
    assert r.status_code == 200
    assert r.json()["status"] == "auto_checked"


# ── PATCH /api/parent/questions/{id} ─────────────────────────────────────────

def test_patch_question_updates_text(tmp_path):
    with patch("medhabhyasah.credentials.keyring", _pin_mock()):
        c, req_id, q_id = _seed_question(tmp_path)
        r = c.patch(
            f"/api/parent/questions/{q_id}",
            json={"question": "Updated question text?"},
            headers={"X-Parent-Pin": "1234"},
        )
        assert r.status_code == 200
        rows = c.get(f"/api/parent/generation-requests/{req_id}/questions",
                     headers={"X-Parent-Pin": "1234"}).json()
    assert rows[0]["question"] == "Updated question text?"


def test_patch_question_updates_options_and_answer(tmp_path):
    with patch("medhabhyasah.credentials.keyring", _pin_mock()):
        c, req_id, q_id = _seed_question(tmp_path)
        r = c.patch(
            f"/api/parent/questions/{q_id}",
            json={"options": ["A", "B", "C", "D"], "answer": 0},
            headers={"X-Parent-Pin": "1234"},
        )
        assert r.status_code == 200
        rows = c.get(f"/api/parent/generation-requests/{req_id}/questions",
                     headers={"X-Parent-Pin": "1234"}).json()
    assert rows[0]["options"] == ["A", "B", "C", "D"]
    assert rows[0]["answer"] == 0


def test_patch_question_rejects_wrong_option_count(tmp_path):
    with patch("medhabhyasah.credentials.keyring", _pin_mock()):
        c, req_id, q_id = _seed_question(tmp_path)
        r = c.patch(
            f"/api/parent/questions/{q_id}",
            json={"options": ["A", "B", "C"]},
            headers={"X-Parent-Pin": "1234"},
        )
    assert r.status_code == 422


def test_patch_question_rejects_bad_answer(tmp_path):
    with patch("medhabhyasah.credentials.keyring", _pin_mock()):
        c, req_id, q_id = _seed_question(tmp_path)
        r = c.patch(
            f"/api/parent/questions/{q_id}",
            json={"answer": 4},
            headers={"X-Parent-Pin": "1234"},
        )
    assert r.status_code == 422


def test_approve_reject_require_pin(tmp_path):
    with patch("medhabhyasah.credentials.keyring", _pin_mock()):
        c, req_id, q_id = _seed_question(tmp_path)
        assert c.post(f"/api/parent/questions/{q_id}/approve").status_code == 401
        assert c.post(f"/api/parent/questions/{q_id}/reject").status_code == 401


# ── Student route: approved-only ──────────────────────────────────────────────

def test_student_questions_returns_only_approved(tmp_path):
    with patch("medhabhyasah.credentials.keyring", _pin_mock()):
        c, req_id, q_id = _seed_question(tmp_path, status="auto_checked")

        # Before approval: student sees nothing
        r_before = c.get("/api/student/questions")
        assert r_before.status_code == 200
        assert r_before.json() == []

        # Approve the question
        c.post(f"/api/parent/questions/{q_id}/approve",
               headers={"X-Parent-Pin": "1234"})

        # After approval: student sees it
        r_after = c.get("/api/student/questions")
        assert r_after.status_code == 200
        data = r_after.json()
        assert len(data) == 1
        assert data[0]["status"] == "approved"


def test_student_questions_excludes_rejected(tmp_path):
    with patch("medhabhyasah.credentials.keyring", _pin_mock()):
        c, req_id, q_id = _seed_question(tmp_path, status="auto_checked")
        c.post(f"/api/parent/questions/{q_id}/reject",
               headers={"X-Parent-Pin": "1234"})
        r = c.get("/api/student/questions")
    assert r.json() == []


def test_student_questions_no_pin_required(tmp_path):
    with patch("medhabhyasah.credentials.keyring", _pin_mock()):
        c, req_id, q_id = _seed_question(tmp_path, status="approved")
        r = c.get("/api/student/questions")
    assert r.status_code == 200


def test_student_questions_filter_by_generation_request(tmp_path):
    from medhabhyasah.db import (
        create_generation_request, create_question, create_schema, get_connection
    )
    conn = get_connection(tmp_path / "test.db")
    create_schema(conn)
    req1 = create_generation_request(conn, subject="Maths", topic="Algebra", grade="9",
                                      exam="CBSE", references_text="", question_count=1)
    req2 = create_generation_request(conn, subject="Science", topic="Cells", grade="7",
                                      exam="CBSE", references_text="", question_count=1)
    create_question(conn, generation_request_id=req1, difficulty="Easy", type_="mcq",
                    question="Q1", options=json.dumps(["A","B","C","D"]), answer="0",
                    explanation="", source_quote="", status="approved")
    create_question(conn, generation_request_id=req2, difficulty="Easy", type_="mcq",
                    question="Q2", options=json.dumps(["A","B","C","D"]), answer="1",
                    explanation="", source_quote="", status="approved")
    conn.close()

    with patch("medhabhyasah.credentials.keyring", _pin_mock()):
        from medhabhyasah.api import create_app
        app = create_app(db_path=tmp_path / "test.db")
        c = TestClient(app)
        r = c.get(f"/api/student/questions?generation_request_id={req1}")
    assert len(r.json()) == 1
    assert r.json()[0]["question"] == "Q1"
