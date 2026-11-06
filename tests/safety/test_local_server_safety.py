"""Safety: the local server resists PIN reset, PIN guessing, DNS rebinding and answer leaks."""
import importlib
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


class _FakeKeyring:
    def __init__(self):
        self.store: dict[str, str] = {}

    def set_password(self, service, user, value):
        self.store[user] = value

    def get_password(self, service, user):
        return self.store.get(user)


@pytest.fixture()
def env(tmp_path: Path):
    """App with first-run setup finished (PIN 4821) and a fake Credential Manager."""
    kr = _FakeKeyring()
    with patch("medhabhyasah.credentials.keyring", kr):
        shared = importlib.import_module("medhabhyasah.api._shared")
        shared._pin_state.update(failures=0, strikes=0, locked_until=0.0)
        from medhabhyasah.api import create_app
        client = TestClient(create_app(db_path=tmp_path / "t.db"))
        assert client.post("/api/setup/pin", json={"pin": "4821"}).status_code == 200
        assert client.post("/api/setup/student",
                           json={"nickname": "S", "grade": "7", "exam": "CBSE"}).status_code == 200
        yield client, kr, shared, tmp_path / "t.db"


# ── Setup routes close after first run ───────────────────────────────────────

def test_setup_routes_refuse_after_setup(env):
    client, kr, _, _ = env
    assert client.post("/api/setup/pin", json={"pin": "0000"}).status_code == 403
    assert client.post("/api/setup/apikey", json={"api_key": "sk-ant-attacker"}).status_code == 403
    assert client.post("/api/setup/student",
                       json={"nickname": "X", "grade": "7", "exam": "CBSE"}).status_code == 403
    assert kr.store["parent-pin"] == "4821"
    assert "anthropic-api-key" not in kr.store


def test_setup_stays_closed_after_all_students_deleted(env):
    client, kr, _, _ = env
    sid = client.get("/api/students").json()[0]["id"]
    assert client.delete(f"/api/parent/students/{sid}", headers={"X-Parent-Pin": "4821"}).status_code == 200
    assert client.get("/api/setup/status").json()["needs_setup"] is False
    assert client.post("/api/setup/pin", json={"pin": "0000"}).status_code == 403
    assert kr.store["parent-pin"] == "4821"


def test_setup_can_be_resumed_before_first_student(tmp_path: Path):
    kr = _FakeKeyring()
    with patch("medhabhyasah.credentials.keyring", kr):
        from medhabhyasah.api import create_app
        client = TestClient(create_app(db_path=tmp_path / "t.db"))
        assert client.post("/api/setup/pin", json={"pin": "1111"}).status_code == 200
        assert client.post("/api/setup/pin", json={"pin": "2222"}).status_code == 200


# ── PIN lockout ──────────────────────────────────────────────────────────────

def _guess(client, pin):
    return client.post("/api/parent/verify-pin", json={"pin": pin}).status_code


def test_lockout_after_five_wrong_pins_even_for_correct_pin(env):
    client, _, _, _ = env
    for _ in range(5):
        assert _guess(client, "0000") == 401
    assert _guess(client, "4821") == 429
    r = client.get("/api/parent/generation-requests", headers={"X-Parent-Pin": "4821"})
    assert r.status_code == 429
    assert int(r.headers["Retry-After"]) > 0


def test_lockout_expires_and_doubles(env):
    client, _, shared, _ = env
    t = [1000.0]
    with patch("medhabhyasah.api._shared.time.monotonic", lambda: t[0]):
        for _ in range(5):
            _guess(client, "0000")
        assert _guess(client, "4821") == 429
        t[0] += 61
        for _ in range(5):                      # second strike: 120 s
            assert _guess(client, "0000") == 401
        t[0] += 61
        assert _guess(client, "4821") == 429    # still locked at 61 s
        t[0] += 60
        assert _guess(client, "4821") == 200    # unlocked after 121 s


def test_correct_pin_resets_failure_count(env):
    client, _, _, _ = env
    for _ in range(4):
        _guess(client, "0000")
    assert _guess(client, "4821") == 200
    for _ in range(4):
        assert _guess(client, "0000") == 401
    assert _guess(client, "4821") == 200


def test_wrong_pin_header_counts_toward_lockout(env):
    client, _, _, _ = env
    for _ in range(5):
        assert client.get("/api/parent/generation-requests",
                          headers={"X-Parent-Pin": "9999"}).status_code == 401
    assert _guess(client, "4821") == 429


# ── Host header (DNS rebinding) ──────────────────────────────────────────────

@pytest.mark.parametrize("host", ["evil.example.com", "evil.example.com:8000", "127.0.0.1.evil.com"])
def test_foreign_host_header_refused(env, host):
    client, _, _, _ = env
    assert client.get("/api/students", headers={"Host": host}).status_code == 400
    assert client.post("/api/setup/pin", json={"pin": "0000"}, headers={"Host": host}).status_code == 400


@pytest.mark.parametrize("host", ["127.0.0.1:51234", "localhost:51234"])
def test_local_host_header_accepted(env, host):
    client, _, _, _ = env
    assert client.get("/api/students", headers={"Host": host}).status_code == 200


# ── Students never receive answers before submitting ─────────────────────────

def test_student_questions_omit_answers(env):
    client, _, _, db_path = env
    from medhabhyasah import db
    with db.get_connection(db_path) as conn:
        rid = db.create_generation_request(conn, "Maths", "t", "7", "CBSE", "", 1)
        db.create_question(conn, rid, "Easy", "mcq", "2+2?", json.dumps(["1", "2", "3", "4"]),
                           "3", "because four", "a quote", status="approved")
    rows = client.get("/api/student/questions").json()
    assert rows and all(k not in rows[0] for k in ("answer", "explanation", "source_quote"))
    assert "because four" not in json.dumps(rows)
