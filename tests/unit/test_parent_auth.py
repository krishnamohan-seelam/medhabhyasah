"""Tests for parent PIN auth middleware and generation form API."""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path: Path):
    from medhabhyasah.api import create_app
    return TestClient(create_app(db_path=tmp_path / "test.db"))


@pytest.fixture()
def authed_client(tmp_path: Path):
    """Client with keyring mocked to always accept PIN '1234'."""
    from medhabhyasah.api import create_app
    app = create_app(db_path=tmp_path / "test.db")
    c = TestClient(app)
    with patch("medhabhyasah.credentials.keyring") as mock_kr:
        mock_kr.get_password = MagicMock(return_value="1234")
        mock_kr.set_password = MagicMock()
        yield c, mock_kr


# ── PIN verification ──────────────────────────────────────────────────────────

def test_verify_pin_correct(authed_client):
    c, _ = authed_client
    r = c.post("/api/parent/verify-pin", json={"pin": "1234"})
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_verify_pin_wrong(authed_client):
    c, mock_kr = authed_client
    mock_kr.get_password = MagicMock(return_value="1234")
    r = c.post("/api/parent/verify-pin", json={"pin": "9999"})
    assert r.status_code == 401


# ── Parent route auth ─────────────────────────────────────────────────────────

def test_generation_requests_no_pin_returns_401(client: TestClient):
    r = client.get("/api/parent/generation-requests")
    assert r.status_code == 401


def test_generation_requests_wrong_pin_returns_401(authed_client):
    c, mock_kr = authed_client
    mock_kr.get_password = MagicMock(return_value="1234")
    r = c.get("/api/parent/generation-requests",
              headers={"X-Parent-Pin": "9999"})
    assert r.status_code == 401


def test_generation_requests_correct_pin_passes(authed_client):
    c, mock_kr = authed_client
    mock_kr.get_password = MagicMock(return_value="1234")
    r = c.get("/api/parent/generation-requests",
              headers={"X-Parent-Pin": "1234"})
    assert r.status_code == 200
    assert isinstance(r.json(), list)


# ── Generation form validation ────────────────────────────────────────────────

def _post_gen(c, mock_kr, body):
    mock_kr.get_password = MagicMock(return_value="1234")
    return c.post(
        "/api/parent/generation-requests",
        json=body,
        headers={"X-Parent-Pin": "1234"},
    )


def test_generation_request_created(authed_client):
    c, mock_kr = authed_client
    r = _post_gen(c, mock_kr, {
        "subject": "Science", "topic": "Photosynthesis",
        "grade": "7", "exam": "CBSE",
        "references_text": "NCERT Class 7 Science",
        "question_count": 10,
    })
    assert r.status_code == 200
    assert r.json()["id"] == 1


def test_generation_invalid_subject_rejected(authed_client):
    c, mock_kr = authed_client
    r = _post_gen(c, mock_kr, {
        "subject": "Dance", "topic": "Photosynthesis",
        "grade": "7", "exam": "CBSE", "question_count": 5,
    })
    assert r.status_code == 422


def test_generation_count_too_high_rejected(authed_client):
    c, mock_kr = authed_client
    r = _post_gen(c, mock_kr, {
        "subject": "Maths", "topic": "Algebra",
        "grade": "9", "exam": "CBSE", "question_count": 51,
    })
    assert r.status_code == 422


def test_generation_count_zero_rejected(authed_client):
    c, mock_kr = authed_client
    r = _post_gen(c, mock_kr, {
        "subject": "Maths", "topic": "Algebra",
        "grade": "9", "exam": "CBSE", "question_count": 0,
    })
    assert r.status_code == 422


def test_past_requests_listed(authed_client):
    c, mock_kr = authed_client
    mock_kr.get_password = MagicMock(return_value="1234")
    _post_gen(c, mock_kr, {
        "subject": "Science", "topic": "Gravity",
        "grade": "8", "exam": "CBSE", "question_count": 5,
    })
    r = c.get("/api/parent/generation-requests",
              headers={"X-Parent-Pin": "1234"})
    assert r.status_code == 200
    reqs = r.json()
    assert len(reqs) == 1
    assert reqs[0]["topic"] == "Gravity"
    assert reqs[0]["subject"] == "Science"
