"""Tests for issue 07: progress, mistakes, practice-mistakes, parent oversight."""
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


def _seed_with_attempt(tmp_path: Path, *, correct_indices=(0,), wrong_indices=(1,)):
    """Create student + 2 approved Easy questions + one submitted attempt."""
    from medhabhyasah.db import (
        create_attempt, create_attempt_answer, create_generation_request,
        create_question, create_schema, create_student, finish_attempt, get_connection,
    )
    conn = get_connection(tmp_path / "test.db")
    create_schema(conn)
    sid = create_student(conn, "Arjun", "9", "CBSE")
    rid = create_generation_request(conn, "Maths", "Algebra", "9", "CBSE", "", 4)
    qids = []
    for i in range(4):
        qid = create_question(
            conn, generation_request_id=rid, difficulty="Easy", type_="mcq",
            question=f"Q{i}?", options=json.dumps(["A", "B", "C", "D"]),
            answer="0", explanation=f"Explanation {i}.", source_quote="", status="approved",
        )
        qids.append(qid)
    attempt_id = create_attempt(conn, student_id=sid, generation_request_id=rid, time_limit_seconds=None)
    score = 0
    for idx in correct_indices:
        create_attempt_answer(conn, attempt_id, qids[idx], chosen_option="0", is_correct=True)
        score += 1
    for idx in wrong_indices:
        create_attempt_answer(conn, attempt_id, qids[idx], chosen_option="1", is_correct=False)
    finish_attempt(conn, attempt_id, score=score, grade="B")
    conn.close()

    from medhabhyasah.api import create_app
    c = TestClient(create_app(db_path=tmp_path / "test.db"))
    return c, sid, rid, attempt_id, qids


# ── Mistakes notebook ─────────────────────────────────────────────────────────

def test_mistakes_returns_only_wrong(tmp_path):
    with patch("medhabhyasah.credentials.keyring", _pin_mock()):
        c, sid, rid, aid, qids = _seed_with_attempt(tmp_path, correct_indices=(0,), wrong_indices=(1, 2))
        r = c.get(f"/api/student/mistakes?student_id={sid}")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 2
    for m in data:
        assert "question" in m
        assert "options" in m
        assert "answer" in m
        assert "explanation" in m


def test_mistakes_deduplicates_repeated_wrong(tmp_path):
    """Same wrong question answered twice still appears once."""
    from medhabhyasah.db import (
        create_attempt, create_attempt_answer, finish_attempt, get_connection,
    )
    with patch("medhabhyasah.credentials.keyring", _pin_mock()):
        c, sid, rid, aid1, qids = _seed_with_attempt(tmp_path, correct_indices=(0,), wrong_indices=(1,))
        conn = get_connection(tmp_path / "test.db")
        aid2 = create_attempt(conn, student_id=sid, generation_request_id=rid, time_limit_seconds=None)
        create_attempt_answer(conn, aid2, qids[1], chosen_option="2", is_correct=False)
        finish_attempt(conn, aid2, score=0, grade="D")
        conn.close()
        r = c.get(f"/api/student/mistakes?student_id={sid}")
    assert len(r.json()) == 1  # still one unique wrong question


def test_mistakes_no_answers_returns_empty(tmp_path):
    from medhabhyasah.db import create_schema, create_student, get_connection
    conn = get_connection(tmp_path / "test.db")
    create_schema(conn)
    sid = create_student(conn, "Empty", "9", "CBSE")
    conn.close()
    with patch("medhabhyasah.credentials.keyring", _pin_mock()):
        from medhabhyasah.api import create_app
        c = TestClient(create_app(db_path=tmp_path / "test.db"))
        r = c.get(f"/api/student/mistakes?student_id={sid}")
    assert r.json() == []


# ── Practice mistakes ─────────────────────────────────────────────────────────

def test_practice_mistakes_creates_attempt_with_wrong_questions(tmp_path):
    with patch("medhabhyasah.credentials.keyring", _pin_mock()):
        c, sid, rid, aid, qids = _seed_with_attempt(tmp_path, correct_indices=(0,), wrong_indices=(1, 2))
        r = c.post("/api/student/practice-mistakes", json={"student_id": sid, "attempt_id": aid})
    assert r.status_code == 200
    data = r.json()
    assert "attempt_id" in data
    assert data["attempt_id"] != aid  # new attempt
    assert data["time_limit_seconds"] is None  # no timer (practice)
    assert len(data["questions"]) == 2
    returned_ids = {q["id"] for q in data["questions"]}
    assert returned_ids == {qids[1], qids[2]}
    # Questions must not contain answer or explanation
    for q in data["questions"]:
        assert "answer" not in q
        assert "explanation" not in q


def test_practice_mistakes_no_wrong_answers_returns_400(tmp_path):
    with patch("medhabhyasah.credentials.keyring", _pin_mock()):
        c, sid, rid, aid, qids = _seed_with_attempt(tmp_path, correct_indices=(0, 1), wrong_indices=())
        r = c.post("/api/student/practice-mistakes", json={"student_id": sid, "attempt_id": aid})
    assert r.status_code == 400


def test_practice_mistakes_wrong_student_returns_403(tmp_path):
    from medhabhyasah.db import create_student, get_connection
    with patch("medhabhyasah.credentials.keyring", _pin_mock()):
        c, sid, rid, aid, qids = _seed_with_attempt(tmp_path, correct_indices=(0,), wrong_indices=(1,))
        conn = get_connection(tmp_path / "test.db")
        other_sid = create_student(conn, "Other", "8", "CBSE")
        conn.close()
        r = c.post("/api/student/practice-mistakes", json={"student_id": other_sid, "attempt_id": aid})
    assert r.status_code == 403


# ── Weak-area summary ─────────────────────────────────────────────────────────

def test_weak_areas_returns_accuracy(tmp_path):
    with patch("medhabhyasah.credentials.keyring", _pin_mock()):
        c, sid, rid, aid, qids = _seed_with_attempt(tmp_path, correct_indices=(0,), wrong_indices=(1,))
        r = c.get(f"/api/parent/weak-areas?student_id={sid}", headers={"X-Parent-Pin": "1234"})
    assert r.status_code == 200
    data = r.json()
    assert len(data) > 0
    row = data[0]
    assert "accuracy_pct" in row
    assert "topic" in row
    assert "difficulty" in row


def test_weak_areas_requires_pin(tmp_path):
    with patch("medhabhyasah.credentials.keyring", _pin_mock()):
        c, sid, rid, aid, qids = _seed_with_attempt(tmp_path)
        r = c.get(f"/api/parent/weak-areas?student_id={sid}")
    assert r.status_code == 401


def test_weak_areas_sorted_ascending(tmp_path):
    """Weakest areas (lowest accuracy) come first."""
    with patch("medhabhyasah.credentials.keyring", _pin_mock()):
        c, sid, rid, aid, qids = _seed_with_attempt(tmp_path, correct_indices=(0,), wrong_indices=(1, 2, 3))
        r = c.get(f"/api/parent/weak-areas?student_id={sid}", headers={"X-Parent-Pin": "1234"})
    data = r.json()
    pcts = [row["accuracy_pct"] for row in data]
    assert pcts == sorted(pcts)
