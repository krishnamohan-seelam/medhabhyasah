"""Safety: model settings never hold or leak keys; open-link accepts known links only."""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import importlib


class _ModelConfigProxy:
    """Safety tests purge medhabhyasah modules from sys.modules; always use the live one."""

    def __getattr__(self, name):
        return getattr(importlib.import_module("medhabhyasah.model_config"), name)


model_config = _ModelConfigProxy()

_KEY = "sk-ant-supersecretkeyvalue"
_PIN = {"X-Parent-Pin": "1234"}


@pytest.fixture()
def client(tmp_path: Path):
    from medhabhyasah.api import create_app
    kr = MagicMock()
    kr.get_password = MagicMock(side_effect=lambda s, u: {
        "anthropic-api-key": _KEY, "parent-pin": "1234"}.get(u))
    with patch("medhabhyasah.credentials.keyring", kr):
        yield TestClient(create_app(db_path=tmp_path / "t.db"))


def test_config_file_never_contains_key(client, tmp_path):
    client.post("/api/parent/settings/model", headers=_PIN,
                json={"provider": "anthropic", "model": "claude-x"})
    client.post("/api/parent/settings/apikey", headers=_PIN, json={"api_key": _KEY})
    assert _KEY not in model_config.get_config_path().read_text(encoding="utf-8")


def test_model_settings_response_never_contains_key(client):
    r = client.get("/api/parent/settings/model", headers=_PIN)
    assert _KEY not in r.text


def test_provider_error_message_never_contains_key():
    from medhabhyasah.generation import ProviderAccessError
    for kind in ("model_unavailable", "key_rejected"):
        assert _KEY not in str(ProviderAccessError(kind, "anthropic", "claude-x"))


def test_open_link_rejects_unknown_urls(client):
    with patch("medhabhyasah.api.parent.webbrowser.open") as opener:
        for url in ("https://evil.example.com", "file:///C:/Windows/System32/calc.exe",
                    "javascript:alert(1)"):
            assert client.post("/api/parent/open-link", headers=_PIN, json={"url": url}).status_code == 400
        opener.assert_not_called()


def test_open_link_accepts_known_link_only_with_pin(client):
    url = model_config.PROVIDERS["anthropic"]["links"][0]["url"]
    with patch("medhabhyasah.api.parent.webbrowser.open") as opener:
        assert client.post("/api/parent/open-link", json={"url": url}).status_code == 401
        assert client.post("/api/parent/open-link", headers=_PIN, json={"url": url}).status_code == 200
        opener.assert_called_once_with(url)


def test_student_routes_do_not_expose_model_settings(client):
    assert client.get("/api/student/settings/model").status_code in (404, 405)
