"""Config-driven model selection and provider-access errors."""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import anthropic
import httpx
import pytest
from fastapi.testclient import TestClient

import importlib


class _ModelConfigProxy:
    """Safety tests purge medhabhyasah modules from sys.modules; always use the live one."""

    def __getattr__(self, name):
        return getattr(importlib.import_module("medhabhyasah.model_config"), name)


model_config = _ModelConfigProxy()

_Q = {
    "difficulty": "Easy", "type": "mcq", "question": "2+2?",
    "options": ["2", "3", "4", "5"], "answer": 2, "explanation": "4", "source_quote": "",
}


def _kr(anthropic_key="sk-ant-secretkey123", gemini_key=None):
    kr = MagicMock()
    kr.get_password = MagicMock(side_effect=lambda s, u: {
        "anthropic-api-key": anthropic_key, "gemini-api-key": gemini_key,
        "parent-pin": "1234",
    }.get(u))
    return kr


def _anthropic_error(cls, status):
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx.Response(status, request=request)
    return cls("boom", response=response, body=None)


# ── Config ────────────────────────────────────────────────────────────────────

def test_defaults_used_when_no_config():
    cfg = model_config.settings_for("anthropic")
    assert cfg.model == model_config.PROVIDERS["anthropic"]["model"]


def test_saved_model_and_prices_are_used():
    model_config.save("anthropic", "claude-future-1", 1.5, 7.5)
    cfg = model_config.settings_for("anthropic")
    assert (cfg.model, cfg.input_cost_per_mtok, cfg.output_cost_per_mtok) == ("claude-future-1", 1.5, 7.5)
    assert model_config.selected_provider() == "anthropic"


def test_bad_model_id_rejected():
    with pytest.raises(ValueError):
        model_config.save("anthropic", "bad model; rm -rf", None, None)


def test_corrupt_config_falls_back_to_defaults():
    model_config.get_config_path().write_text("{not json", encoding="utf-8")
    assert model_config.settings_for("gemini").model == model_config.PROVIDERS["gemini"]["model"]
    assert model_config.selected_provider() is None


def test_generation_uses_configured_model_and_prices():
    model_config.save("anthropic", "claude-future-1", 1.0, 2.0)
    text = MagicMock(type="text", text=json.dumps([_Q]))
    response = MagicMock(content=[text], usage=MagicMock(input_tokens=1_000_000, output_tokens=1_000_000))
    with patch("medhabhyasah.generation.anthropic.Anthropic") as MockA, \
            patch("medhabhyasah.credentials.keyring", _kr()):
        MockA.return_value.messages.create.return_value = response
        from medhabhyasah.generation import generate_questions
        result = generate_questions("Maths", "Algebra", "9", "CBSE", "", 1)
    assert MockA.return_value.messages.create.call_args.kwargs["model"] == "claude-future-1"
    assert abs(result.api_cost_usd - 3.0) < 1e-9


def test_parent_choice_wins_when_both_keys_stored():
    model_config.save("gemini", "gemini-future", None, None)
    with patch("medhabhyasah.credentials.keyring", _kr(gemini_key="AIzaKey")):
        from medhabhyasah import credentials
        assert credentials.configured_provider() == "anthropic"
        assert (model_config.selected_provider() or credentials.configured_provider()) == "gemini"


# ── Provider errors ───────────────────────────────────────────────────────────

def test_retired_anthropic_model_raises_model_unavailable():
    err = _anthropic_error(anthropic.NotFoundError, 404)
    with patch("medhabhyasah.generation.anthropic.Anthropic") as MockA, \
            patch("medhabhyasah.credentials.keyring", _kr()):
        MockA.return_value.messages.create.side_effect = err
        from medhabhyasah.generation import ProviderAccessError, generate_questions
        with pytest.raises(ProviderAccessError) as info:
            generate_questions("Maths", "Algebra", "9", "CBSE", "", 1)
    assert info.value.kind == "model_unavailable"
    assert info.value.model == model_config.PROVIDERS["anthropic"]["model"]
    urls = [link["url"] for link in info.value.to_dict()["links"]]
    assert all(u.startswith("https://") for u in urls) and urls


def test_rejected_anthropic_key_raises_key_rejected():
    err = _anthropic_error(anthropic.AuthenticationError, 401)
    with patch("medhabhyasah.generation.anthropic.Anthropic") as MockA, \
            patch("medhabhyasah.credentials.keyring", _kr()):
        MockA.return_value.messages.create.side_effect = err
        from medhabhyasah.generation import ProviderAccessError, generate_questions
        with pytest.raises(ProviderAccessError) as info:
            generate_questions("Maths", "Algebra", "9", "CBSE", "", 1)
    assert info.value.kind == "key_rejected"


def test_gemini_404_raises_model_unavailable():
    class ClientError(Exception):
        code = 404

    client = MagicMock()
    client.models.generate_content.side_effect = ClientError("models/x is not found")
    genai = MagicMock()
    genai.Client.return_value = client
    with patch("medhabhyasah.credentials.keyring", _kr(anthropic_key=None, gemini_key="AIzaKey")), \
            patch.dict("sys.modules", {
                "google": MagicMock(genai=genai), "google.genai": genai,
                "google.genai.types": MagicMock()}):
        from medhabhyasah.generation import ProviderAccessError, generate_questions
        with pytest.raises(ProviderAccessError) as info:
            generate_questions("Maths", "Algebra", "9", "CBSE", "", 1)
    assert info.value.kind == "model_unavailable"
    assert info.value.provider == "gemini"


# ── Routes ────────────────────────────────────────────────────────────────────

@pytest.fixture()
def client(tmp_path: Path):
    from medhabhyasah.api import create_app
    with patch("medhabhyasah.credentials.keyring", _kr()):
        yield TestClient(create_app(db_path=tmp_path / "t.db"))


_PIN = {"X-Parent-Pin": "1234"}


def test_model_settings_require_pin(client):
    assert client.get("/api/parent/settings/model").status_code == 401
    assert client.post("/api/parent/settings/model", json={"provider": "gemini", "model": "m"}).status_code == 401


def test_model_settings_roundtrip(client):
    r = client.post("/api/parent/settings/model", headers=_PIN,
                    json={"provider": "gemini", "model": "gemini-next", "input_cost_per_mtok": 0.2,
                          "output_cost_per_mtok": 0.8})
    assert r.status_code == 200
    data = client.get("/api/parent/settings/model", headers=_PIN).json()
    assert data["selected"] == "gemini"
    assert data["providers"]["gemini"]["model"] == "gemini-next"
    assert data["providers"]["anthropic"]["has_key"] is True


def test_model_settings_reject_bad_model(client):
    r = client.post("/api/parent/settings/model", headers=_PIN,
                    json={"provider": "gemini", "model": "no spaces allowed"})
    assert r.status_code == 400


def test_generate_route_reports_provider_issue(client):
    r = client.post("/api/parent/generation-requests", headers=_PIN, json={
        "subject": "Maths", "topic": "Algebra", "grade": "9", "exam": "CBSE", "question_count": 5})
    req_id = r.json()["id"]
    err = _anthropic_error(anthropic.NotFoundError, 404)
    with patch("medhabhyasah.generation.anthropic.Anthropic") as MockA:
        MockA.return_value.messages.create.side_effect = err
        r = client.post(f"/api/parent/generation-requests/{req_id}/generate", headers=_PIN)
    event = json.loads(r.text.split("data: ", 2)[-1].strip().split("\n")[0])
    assert event["provider_issue"]["kind"] == "model_unavailable"
    assert event["provider_issue"]["links"]
    # failed requests can be retried after the parent fixes the model
    status = client.get(f"/api/parent/generation-requests/{req_id}", headers=_PIN).json()["status"]
    assert status == "failed"
