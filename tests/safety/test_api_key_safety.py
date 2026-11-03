"""Safety: API key must never appear in any API response body."""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

_FAKE_KEY = "sk-ant-fakekeyfortest99"


@pytest.fixture()
def client(tmp_path: Path):
    from medhabhyasah.api import create_app
    app = create_app(db_path=tmp_path / "test.db")
    # Pre-store fake key via mocked keyring
    with patch("medhabhyasah.credentials.keyring") as mock_kr:
        mock_kr.set_password = MagicMock()
        mock_kr.get_password = MagicMock(return_value=_FAKE_KEY)
        c = TestClient(app)
        c.post("/api/setup/pin", json={"pin": "1234"})
        c.post("/api/setup/apikey", json={"api_key": _FAKE_KEY})
        c.post("/api/setup/student", json={"nickname": "Test", "grade": "7", "exam": "CBSE"})
    return c


_ROUTES_TO_CHECK = [
    ("GET", "/"),
    ("GET", "/api/setup/status"),
    ("GET", "/api/students"),
]


@pytest.mark.parametrize("method,path", _ROUTES_TO_CHECK)
def test_api_key_absent_from_response(client: TestClient, method: str, path: str):
    r = getattr(client, method.lower())(path)
    assert _FAKE_KEY not in r.text, (
        f"API key leaked in {method} {path} response"
    )
