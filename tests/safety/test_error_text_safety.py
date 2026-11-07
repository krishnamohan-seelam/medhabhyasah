"""Safety: provider error text never reaches the screen, and the log never holds keys."""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import anthropic
import httpx
import pytest
from fastapi.testclient import TestClient

_ANT_KEY = "sk-ant-api03-REALLOOKINGSECRET0123456789"
_ODD_KEY = "custom-format-key-ZZZ987654321"   # stored key with no known prefix
_GEM_KEY = "AIzaSyFAKEFAKEFAKEFAKEFAKEFAKE12345"
_OPENAI_KEY = "sk-FAKEOPENAIKEYLOOKINGSECRET0123456789"
_PIN = {"X-Parent-Pin": "1234"}


def _kr():
    kr = MagicMock()
    kr.get_password = MagicMock(side_effect=lambda s, u: {
        "anthropic-api-key": _ODD_KEY, "gemini-api-key": None,
        "openai-api-key": None, "parent-pin": "1234"}.get(u))
    return kr


def _leaky(cls=Exception, status=None, text=""):
    """An error whose text carries keys in several shapes, as a bad proxy or SDK might."""
    body = (f"{text} x-api-key: {_ANT_KEY} key={_GEM_KEY} Authorization: Bearer abc123def456ghi "
            f"stored={_ODD_KEY} openai={_OPENAI_KEY}")
    if status is None:
        return cls(body)
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    return cls(body, response=httpx.Response(status, request=request), body=None)


@pytest.fixture()
def client(tmp_path: Path):
    from medhabhyasah.api import create_app
    with patch("medhabhyasah.credentials.keyring", _kr()):
        yield TestClient(create_app(db_path=tmp_path / "t.db"))


def _run_generation(client, error):
    req_id = client.post("/api/parent/generation-requests", headers=_PIN, json={
        "subject": "Maths", "topic": "Algebra", "grade": "9", "exam": "CBSE",
        "question_count": 5}).json()["id"]
    with patch("medhabhyasah.generation.anthropic.Anthropic") as MockA:
        MockA.return_value.messages.create.side_effect = error
        r = client.post(f"/api/parent/generation-requests/{req_id}/generate", headers=_PIN)
    last = [ln for ln in r.text.split("\n") if ln.startswith("data: ")][-1]
    return json.loads(last[6:]), r.text


def _log_text() -> str:
    from medhabhyasah import safe_log
    path = safe_log.get_data_dir() / safe_log.LOG_NAME
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _flush_log():
    import logging
    for h in logging.getLogger("medhabhyasah.errors").handlers:
        h.flush()


_KEYS = (_ANT_KEY, _ODD_KEY, _GEM_KEY, _OPENAI_KEY, "abc123def456ghi")


@pytest.mark.parametrize("error", [
    _leaky(),
    _leaky(anthropic.RateLimitError, 429),
    _leaky(anthropic.InternalServerError, 500),
    _leaky(anthropic.BadRequestError, 400, "Your credit balance is too low"),
    _leaky(ValueError),
    _leaky(RuntimeError),
])
def test_no_key_on_screen_or_in_log(client, error):
    event, raw = _run_generation(client, error)
    _flush_log()
    log = _log_text()
    for key in _KEYS:
        assert key not in raw, f"{key} reached the screen"
        assert key not in log, f"{key} reached the log"
    assert "x-api-key" not in event["error"].lower()
    assert "failure_kind" in event


def test_unknown_error_shows_only_fixed_message_and_logs_detail(client):
    event, raw = _run_generation(client, RuntimeError("secret internal detail 42"))
    _flush_log()
    assert event["failure_kind"] == "unknown"
    assert "secret internal detail" not in raw
    assert "medhabhyasah.log" in event["error"]
    assert "secret internal detail 42" in _log_text()


def test_scrub_removes_stored_and_pattern_keys_and_caps_length():
    with patch("medhabhyasah.credentials.keyring", _kr()):
        from medhabhyasah import safe_log
        out = safe_log.scrub(
            f"a {_ODD_KEY} b {_ANT_KEY} c {_GEM_KEY} d {_OPENAI_KEY} " + "x" * 10_000
        )
    assert not any(k in out for k in (_ODD_KEY, _ANT_KEY, _GEM_KEY, _OPENAI_KEY))
    assert len(out) < 4100


def test_log_failure_never_breaks_generation(client):
    with patch("medhabhyasah.safe_log._logger", side_effect=OSError("disk full")):
        event, _ = _run_generation(client, RuntimeError("boom"))
    assert event["failure_kind"] == "unknown"
