"""Tests for DB schema creation."""
import sqlite3

import pytest

from medhabhyasah.db import create_schema

EXPECTED_TABLES = {
    "students",
    "generation_requests",
    "questions",
    "attempts",
    "attempt_answers",
}


def _tables(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    return {r[0] for r in rows}


def test_all_five_tables_created():
    conn = sqlite3.connect(":memory:")
    create_schema(conn)
    assert EXPECTED_TABLES <= _tables(conn)


def test_schema_creation_is_idempotent():
    conn = sqlite3.connect(":memory:")
    create_schema(conn)
    create_schema(conn)  # second call must not raise
    assert EXPECTED_TABLES <= _tables(conn)


def test_students_columns():
    conn = sqlite3.connect(":memory:")
    create_schema(conn)
    info = conn.execute("PRAGMA table_info(students)").fetchall()
    col_names = {row[1] for row in info}
    assert {"id", "nickname", "grade", "exam", "created_at"} <= col_names


def test_questions_status_default_is_draft():
    conn = sqlite3.connect(":memory:")
    create_schema(conn)
    conn.execute(
        "INSERT INTO generation_requests (topic, grade, exam, question_count) "
        "VALUES ('test', '7', 'CBSE', 5)"
    )
    conn.execute(
        "INSERT INTO questions "
        "(generation_request_id, difficulty, type, question, options, answer) "
        "VALUES (1, 'Easy', 'MCQ', 'Q?', '[]', 'A')"
    )
    row = conn.execute("SELECT status FROM questions WHERE id=1").fetchone()
    assert row[0] == "draft"
