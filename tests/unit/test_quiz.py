"""Tests for quiz session — issue 06: student quiz flow."""
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


def _seed(tmp_path: Path, *, difficulties=("Easy",), n_per=2):
    """Seed a generation request with approved questions of given difficulties."""
    from medhabhyasah.db import (
        create_generation_request, create_question, create_schema, get_connection,
        create_student,
    )
    conn = get_connection(tmp_path / "test.db")
    create_schema(conn)
    student_id = create_student(conn, nickname="Arjun", grade="9", exam="CBSE")
    req_id = create_generation_request(
        conn, subject="Maths", topic="Algebra", grade="9",
        exam="CBSE", references_text="", question_count=10,
    )
    for diff in difficulties:
        for i in range(n_per):
            create_question(
                conn,
                generation_request_id=req_id,
                difficulty=diff, type_="mcq",
                question=f"Q {diff} {i}?",
                options=json.dumps(["A", "B", "C", "D"]),
                answer="0",
                explanation="Because A.",
                source_quote="", status="approved",
            )
    conn.close()

    from medhabhyasah.api import create_app
    app = create_app(db_path=tmp_path / "test.db")
    return TestClient(app), student_id, req_id


# ── Topic endpoint ────────────────────────────────────────────────────────────

def test_topics_returns_approved_counts(tmp_path):
    with patch("medhabhyasah.credentials.keyring", _pin_mock()):
        c, sid, rid = _seed(tmp_path, difficulties=("Easy", "Medium"), n_per=3)
        r = c.get("/api/student/topics")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    row = data[0]
    assert row["generation_request_id"] == rid
    assert row["total_approved"] == 6
    assert row["easy_count"] == 3
    assert row["medium_count"] == 3
    assert row["hard_count"] == 0


def test_topics_filter_by_subject(tmp_path):
    from medhabhyasah.db import (
        create_generation_request, create_question, create_schema, get_connection,
    )
    conn = get_connection(tmp_path / "test.db")
    create_schema(conn)
    req1 = create_generation_request(conn, subject="Maths",   topic="Algebra", grade="9", exam="CBSE", references_text="", question_count=1)
    req2 = create_generation_request(conn, subject="Science", topic="Cells",   grade="9", exam="CBSE", references_text="", question_count=1)
    for req in (req1, req2):
        create_question(conn, generation_request_id=req, difficulty="Easy", type_="mcq",
                        question="Q?", options=json.dumps(["A","B","C","D"]), answer="0",
                        explanation="", source_quote="", status="approved")
    conn.close()

    with patch("medhabhyasah.credentials.keyring", _pin_mock()):
        from medhabhyasah.api import create_app
        c = TestClient(create_app(db_path=tmp_path / "test.db"))
        r = c.get("/api/student/topics?subject=Maths")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["generation_request_id"] == req1


# ── Attempt creation ──────────────────────────────────────────────────────────

def test_start_attempt_returns_questions(tmp_path):
    with patch("medhabhyasah.credentials.keyring", _pin_mock()):
        c, sid, rid = _seed(tmp_path, difficulties=("Easy",), n_per=4)
        r = c.post("/api/student/attempts", json={
            "student_id": sid, "generation_request_id": rid,
            "mode": "practice", "question_count": 3,
        })
    assert r.status_code == 200
    d = r.json()
    assert "attempt_id" in d
    assert len(d["questions"]) == 3
    # Questions must NOT contain answer or explanation
    for q in d["questions"]:
        assert "answer" not in q
        assert "explanation" not in q
    # No time limit for practice
    assert d["time_limit_seconds"] is None


def test_start_attempt_challenge_has_timer(tmp_path):
    with patch("medhabhyasah.credentials.keyring", _pin_mock()):
        c, sid, rid = _seed(tmp_path, difficulties=("Medium",), n_per=4)
        r = c.post("/api/student/attempts", json={
            "student_id": sid, "generation_request_id": rid,
            "mode": "challenge", "question_count": 2,
        })
    assert r.status_code == 200
    # 90 s/q × 2 q
    assert r.json()["time_limit_seconds"] == 180


def test_start_attempt_exam_has_timer(tmp_path):
    with patch("medhabhyasah.credentials.keyring", _pin_mock()):
        c, sid, rid = _seed(tmp_path, difficulties=("Easy",), n_per=4)
        r = c.post("/api/student/attempts", json={
            "student_id": sid, "generation_request_id": rid,
            "mode": "exam", "question_count": 2,
        })
    assert r.status_code == 200
    # 60 s/q × 2 q
    assert r.json()["time_limit_seconds"] == 120


def test_start_attempt_rejects_too_many(tmp_path):
    with patch("medhabhyasah.credentials.keyring", _pin_mock()):
        c, sid, rid = _seed(tmp_path, difficulties=("Easy",), n_per=1)
        r = c.post("/api/student/attempts", json={
            "student_id": sid, "generation_request_id": rid,
            "mode": "practice", "question_count": 5,
        })
    assert r.status_code == 400


def test_start_attempt_mode_filters_difficulty(tmp_path):
    """Practice mode should not serve Medium/Hard questions."""
    with patch("medhabhyasah.credentials.keyring", _pin_mock()):
        c, sid, rid = _seed(tmp_path, difficulties=("Medium",), n_per=3)
        r = c.post("/api/student/attempts", json={
            "student_id": sid, "generation_request_id": rid,
            "mode": "practice", "question_count": 2,
        })
    # No Easy questions in the seed → 400
    assert r.status_code == 400


# ── Attempt submission ────────────────────────────────────────────────────────

def _start(c, sid, rid, mode="practice", count=2):
    r = c.post("/api/student/attempts", json={
        "student_id": sid, "generation_request_id": rid,
        "mode": mode, "question_count": count,
    })
    assert r.status_code == 200, r.text
    return r.json()


def test_submit_all_correct(tmp_path):
    with patch("medhabhyasah.credentials.keyring", _pin_mock()):
        c, sid, rid = _seed(tmp_path, difficulties=("Easy",), n_per=4)
        attempt = _start(c, sid, rid, count=2)
        answers = [{"question_id": q["id"], "chosen_option": 0} for q in attempt["questions"]]
        r = c.post(f"/api/student/attempts/{attempt['attempt_id']}/submit", json={"answers": answers})
    assert r.status_code == 200
    d = r.json()
    assert d["score"] == 2
    assert d["total"] == 2
    assert d["grade"] == "A"
    assert d["pct"] == 100.0


def test_submit_all_wrong(tmp_path):
    with patch("medhabhyasah.credentials.keyring", _pin_mock()):
        c, sid, rid = _seed(tmp_path, difficulties=("Easy",), n_per=4)
        attempt = _start(c, sid, rid, count=2)
        # answer is always 0; submit 1 (wrong)
        answers = [{"question_id": q["id"], "chosen_option": 1} for q in attempt["questions"]]
        r = c.post(f"/api/student/attempts/{attempt['attempt_id']}/submit", json={"answers": answers})
    assert r.status_code == 200
    d = r.json()
    assert d["score"] == 0
    assert d["grade"] == "D"


def test_submit_skipped_questions(tmp_path):
    with patch("medhabhyasah.credentials.keyring", _pin_mock()):
        c, sid, rid = _seed(tmp_path, difficulties=("Easy",), n_per=4)
        attempt = _start(c, sid, rid, count=2)
        answers = [{"question_id": q["id"], "chosen_option": None} for q in attempt["questions"]]
        r = c.post(f"/api/student/attempts/{attempt['attempt_id']}/submit", json={"answers": answers})
    assert r.status_code == 200
    d = r.json()
    assert d["score"] == 0
    for item in d["breakdown"]:
        assert item["chosen_option"] is None


def test_submit_returns_breakdown_with_explanation(tmp_path):
    with patch("medhabhyasah.credentials.keyring", _pin_mock()):
        c, sid, rid = _seed(tmp_path, difficulties=("Easy",), n_per=4)
        attempt = _start(c, sid, rid, count=2)
        answers = [{"question_id": q["id"], "chosen_option": 1} for q in attempt["questions"]]
        r = c.post(f"/api/student/attempts/{attempt['attempt_id']}/submit", json={"answers": answers})
    assert r.status_code == 200
    for item in r.json()["breakdown"]:
        assert "explanation" in item
        assert "correct_answer" in item
        assert "options" in item


def test_double_submit_rejected(tmp_path):
    with patch("medhabhyasah.credentials.keyring", _pin_mock()):
        c, sid, rid = _seed(tmp_path, difficulties=("Easy",), n_per=4)
        attempt = _start(c, sid, rid, count=2)
        answers = [{"question_id": q["id"], "chosen_option": 0} for q in attempt["questions"]]
        aid = attempt["attempt_id"]
        c.post(f"/api/student/attempts/{aid}/submit", json={"answers": answers})
        r2 = c.post(f"/api/student/attempts/{aid}/submit", json={"answers": answers})
    assert r2.status_code == 400


def test_list_attempts(tmp_path):
    with patch("medhabhyasah.credentials.keyring", _pin_mock()):
        c, sid, rid = _seed(tmp_path, difficulties=("Easy",), n_per=4)
        attempt = _start(c, sid, rid, count=2)
        answers = [{"question_id": q["id"], "chosen_option": 0} for q in attempt["questions"]]
        c.post(f"/api/student/attempts/{attempt['attempt_id']}/submit", json={"answers": answers})
        r = c.get(f"/api/student/attempts?student_id={sid}")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["score"] == 2
