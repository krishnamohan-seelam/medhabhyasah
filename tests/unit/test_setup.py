"""Tests for first-run setup: DB helpers, API routes, and mock keyring."""
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from medhabhyasah.db import (
    count_students,
    create_schema,
    create_student,
    list_students,
)


# ── DB helper tests ───────────────────────────────────────────────────────────

def _mem_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    create_schema(conn)
    return conn


def test_count_students_empty():
    assert count_students(_mem_conn()) == 0


def test_create_student_returns_id():
    conn = _mem_conn()
    sid = create_student(conn, "Arjun", "7", "CBSE")
    assert sid == 1


def test_create_student_increments_count():
    conn = _mem_conn()
    create_student(conn, "Arjun", "7", "CBSE")
    create_student(conn, "Priya", "9", "ICSE")
    assert count_students(conn) == 2


def test_list_students_returns_dicts():
    conn = _mem_conn()
    create_student(conn, "Arjun", "7", "CBSE")
    rows = list_students(conn)
    assert len(rows) == 1
    assert rows[0]["nickname"] == "Arjun"
    assert rows[0]["grade"] == "7"
    assert rows[0]["exam"] == "CBSE"


# ── API route tests ────────────────────────────────────────────────────────────

@pytest.fixture()
def client(tmp_path: Path):
    from medhabhyasah.api import create_app
    return TestClient(create_app(db_path=tmp_path / "test.db"))


def test_setup_status_needs_setup_initially(client: TestClient):
    r = client.get("/api/setup/status")
    assert r.status_code == 200
    assert r.json()["needs_setup"] is True


def test_setup_status_no_setup_after_student_created(tmp_path: Path):
    from medhabhyasah.api import create_app
    db = tmp_path / "test.db"
    app = create_app(db_path=db)
    c = TestClient(app)
    with patch("medhabhyasah.credentials.keyring") as mock_kr:
        mock_kr.set_password = MagicMock()
        c.post("/api/setup/pin", json={"pin": "1234"})
        c.post("/api/setup/apikey", json={"api_key": "sk-ant-test123"})
        c.post("/api/setup/student", json={"nickname": "Arjun", "grade": "7", "exam": "CBSE"})
    r = c.get("/api/setup/status")
    assert r.json()["needs_setup"] is False


def test_setup_pin_invalid_rejected(client: TestClient):
    r = client.post("/api/setup/pin", json={"pin": "abc"})
    assert r.status_code == 422


def test_setup_pin_too_short_rejected(client: TestClient):
    r = client.post("/api/setup/pin", json={"pin": "12"})
    assert r.status_code == 422


def test_setup_apikey_bad_prefix_rejected(client: TestClient):
    r = client.post("/api/setup/apikey", json={"api_key": "not-an-anthropic-key"})
    assert r.status_code == 422


def test_setup_student_blank_nickname_rejected(client: TestClient):
    r = client.post("/api/setup/student", json={"nickname": "", "grade": "7", "exam": "CBSE"})
    assert r.status_code == 422


# ── Credential Manager round-trip (mocked keyring) ───────────────────────────

def test_pin_stored_in_keyring(client: TestClient):
    with patch("medhabhyasah.credentials.keyring") as mock_kr:
        mock_kr.set_password = MagicMock()
        r = client.post("/api/setup/pin", json={"pin": "5678"})
    assert r.status_code == 200
    mock_kr.set_password.assert_called_once_with("medhabhyasah", "parent-pin", "5678")


def test_api_key_stored_in_keyring(client: TestClient):
    with patch("medhabhyasah.credentials.keyring") as mock_kr:
        mock_kr.set_password = MagicMock()
        r = client.post("/api/setup/apikey", json={"api_key": "sk-ant-validkey"})
    assert r.status_code == 200
    mock_kr.set_password.assert_called_once_with(
        "medhabhyasah", "anthropic-api-key", "sk-ant-validkey"
    )


def test_verify_pin_mocked():
    with patch("medhabhyasah.credentials.keyring") as mock_kr:
        mock_kr.get_password = MagicMock(return_value="1234")
        from medhabhyasah.credentials import verify_pin
        assert verify_pin("1234") is True
        assert verify_pin("9999") is False
