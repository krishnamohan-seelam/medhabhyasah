"""Tests for issue 08: student profile management and PIN change."""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


def _pin_mock(pin="1234"):
    m = MagicMock()
    m.get_password = MagicMock(return_value=pin)
    m.set_password = MagicMock()
    return m


def _make_app(tmp_path: Path):
    from medhabhyasah.api import create_app
    from medhabhyasah.db import create_schema, get_connection
    conn = get_connection(tmp_path / "test.db")
    create_schema(conn)
    conn.close()
    return TestClient(create_app(db_path=tmp_path / "test.db"))


def _seed_student(tmp_path: Path, nickname="Arjun", grade="9", exam="CBSE"):
    from medhabhyasah.db import create_student, get_connection
    conn = get_connection(tmp_path / "test.db")
    sid = create_student(conn, nickname, grade, exam)
    conn.close()
    return sid


# ── Add student ───────────────────────────────────────────────────────────────

def test_add_student_creates_profile(tmp_path):
    with patch("medhabhyasah.credentials.keyring", _pin_mock()):
        c = _make_app(tmp_path)
        r = c.post("/api/parent/students",
                   json={"nickname": "Priya", "grade": "8", "exam": "CBSE"},
                   headers={"X-Parent-Pin": "1234"})
    assert r.status_code == 200
    assert r.json()["nickname"] == "Priya"


def test_add_student_appears_in_list(tmp_path):
    with patch("medhabhyasah.credentials.keyring", _pin_mock()):
        c = _make_app(tmp_path)
        c.post("/api/parent/students",
               json={"nickname": "Rohit", "grade": "10", "exam": "ICSE"},
               headers={"X-Parent-Pin": "1234"})
        students = c.get("/api/students").json()
    assert any(s["nickname"] == "Rohit" for s in students)


def test_add_student_requires_pin(tmp_path):
    with patch("medhabhyasah.credentials.keyring", _pin_mock()):
        c = _make_app(tmp_path)
        r = c.post("/api/parent/students",
                   json={"nickname": "Priya", "grade": "8", "exam": "CBSE"})
    assert r.status_code == 401


# ── Edit student ──────────────────────────────────────────────────────────────

def test_edit_student_updates_fields(tmp_path):
    from medhabhyasah.db import create_schema, get_connection
    conn = get_connection(tmp_path / "test.db")
    create_schema(conn)
    conn.close()
    with patch("medhabhyasah.credentials.keyring", _pin_mock()):
        c = _make_app(tmp_path)
        sid = _seed_student(tmp_path, nickname="Arjun", grade="9", exam="CBSE")
        r = c.patch(f"/api/parent/students/{sid}",
                    json={"nickname": "Arjun Kumar", "grade": "10", "exam": "CBSE"},
                    headers={"X-Parent-Pin": "1234"})
    assert r.status_code == 200
    assert r.json()["nickname"] == "Arjun Kumar"
    assert r.json()["grade"] == "10"


def test_edit_student_requires_pin(tmp_path):
    from medhabhyasah.db import create_schema, get_connection
    conn = get_connection(tmp_path / "test.db")
    create_schema(conn)
    conn.close()
    with patch("medhabhyasah.credentials.keyring", _pin_mock()):
        c = _make_app(tmp_path)
        sid = _seed_student(tmp_path)
        r = c.patch(f"/api/parent/students/{sid}",
                    json={"nickname": "X", "grade": "9", "exam": "CBSE"})
    assert r.status_code == 401


# ── Delete student ────────────────────────────────────────────────────────────

def test_delete_student_no_attempts(tmp_path):
    from medhabhyasah.db import create_schema, get_connection
    conn = get_connection(tmp_path / "test.db")
    create_schema(conn)
    conn.close()
    with patch("medhabhyasah.credentials.keyring", _pin_mock()):
        c = _make_app(tmp_path)
        sid = _seed_student(tmp_path)
        r = c.delete(f"/api/parent/students/{sid}", headers={"X-Parent-Pin": "1234"})
    assert r.status_code == 200
    assert r.json()["deleted"] == sid


def test_delete_student_with_attempts_returns_409(tmp_path):
    from medhabhyasah.db import (
        create_attempt, create_generation_request, create_question, create_schema, get_connection,
    )
    conn = get_connection(tmp_path / "test.db")
    create_schema(conn)
    conn.close()
    with patch("medhabhyasah.credentials.keyring", _pin_mock()):
        c = _make_app(tmp_path)
        sid = _seed_student(tmp_path)
        conn = get_connection(tmp_path / "test.db")
        rid = create_generation_request(conn, "Maths", "Algebra", "9", "CBSE", "", 1)
        create_attempt(conn, student_id=sid, generation_request_id=rid, time_limit_seconds=None)
        conn.close()
        r = c.delete(f"/api/parent/students/{sid}", headers={"X-Parent-Pin": "1234"})
    assert r.status_code == 409


def test_delete_student_force_cascades(tmp_path):
    from medhabhyasah.db import (
        create_attempt, create_attempt_answer, create_generation_request,
        create_question, create_schema, get_connection, list_students,
    )
    conn = get_connection(tmp_path / "test.db")
    create_schema(conn)
    conn.close()
    with patch("medhabhyasah.credentials.keyring", _pin_mock()):
        c = _make_app(tmp_path)
        sid = _seed_student(tmp_path)
        conn = get_connection(tmp_path / "test.db")
        rid = create_generation_request(conn, "Maths", "Algebra", "9", "CBSE", "", 1)
        qid = create_question(conn, rid, "Easy", "mcq", "Q?",
                              json.dumps(["A","B","C","D"]), "0", "", "", "approved")
        aid = create_attempt(conn, student_id=sid, generation_request_id=rid, time_limit_seconds=None)
        create_attempt_answer(conn, aid, qid, chosen_option="0", is_correct=True)
        conn.close()
        r = c.delete(f"/api/parent/students/{sid}?force=true", headers={"X-Parent-Pin": "1234"})
    assert r.status_code == 200
    # Student is gone
    conn = get_connection(tmp_path / "test.db")
    remaining = list_students(conn)
    conn.close()
    assert not any(s["id"] == sid for s in remaining)


def test_delete_student_requires_pin(tmp_path):
    from medhabhyasah.db import create_schema, get_connection
    conn = get_connection(tmp_path / "test.db")
    create_schema(conn)
    conn.close()
    with patch("medhabhyasah.credentials.keyring", _pin_mock()):
        c = _make_app(tmp_path)
        sid = _seed_student(tmp_path)
        r = c.delete(f"/api/parent/students/{sid}")
    assert r.status_code == 401


# ── PIN change ────────────────────────────────────────────────────────────────

def test_change_pin_succeeds(tmp_path):
    mock_kr = MagicMock()
    mock_kr.get_password = MagicMock(return_value="1234")
    mock_kr.set_password = MagicMock()
    with patch("medhabhyasah.credentials.keyring", mock_kr):
        c = _make_app(tmp_path)
        r = c.post("/api/parent/settings/pin",
                   json={"new_pin": "5678", "confirm_pin": "5678"},
                   headers={"X-Parent-Pin": "1234"})
    assert r.status_code == 200
    assert r.json()["ok"] is True
    mock_kr.set_password.assert_called_once()


def test_change_pin_mismatched_confirms_rejected(tmp_path):
    with patch("medhabhyasah.credentials.keyring", _pin_mock()):
        c = _make_app(tmp_path)
        r = c.post("/api/parent/settings/pin",
                   json={"new_pin": "5678", "confirm_pin": "9999"},
                   headers={"X-Parent-Pin": "1234"})
    assert r.status_code == 400


def test_change_pin_wrong_old_pin_rejected(tmp_path):
    with patch("medhabhyasah.credentials.keyring", _pin_mock()):
        c = _make_app(tmp_path)
        r = c.post("/api/parent/settings/pin",
                   json={"new_pin": "5678", "confirm_pin": "5678"},
                   headers={"X-Parent-Pin": "wrong"})
    assert r.status_code == 401


def test_change_pin_invalid_format_rejected(tmp_path):
    with patch("medhabhyasah.credentials.keyring", _pin_mock()):
        c = _make_app(tmp_path)
        r = c.post("/api/parent/settings/pin",
                   json={"new_pin": "abc", "confirm_pin": "abc"},
                   headers={"X-Parent-Pin": "1234"})
    assert r.status_code == 422
