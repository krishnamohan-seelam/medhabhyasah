"""Tests for static font serving via the FastAPI app."""
import pytest
from fastapi.testclient import TestClient

from medhabhyasah.api import create_app


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


def test_regular_font_returns_200(client: TestClient) -> None:
    resp = client.get("/static/fonts/SourceSans3-Regular.woff2")
    assert resp.status_code == 200


def test_semibold_font_returns_200(client: TestClient) -> None:
    resp = client.get("/static/fonts/SourceSans3-SemiBold.woff2")
    assert resp.status_code == 200


def test_font_content_type_is_woff2(client: TestClient) -> None:
    resp = client.get("/static/fonts/SourceSans3-Regular.woff2")
    assert resp.headers.get("content-type", "") == "font/woff2"


def test_home_route_returns_200(client: TestClient) -> None:
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Medhabhyasah" in resp.text


def test_home_has_local_font_face(client: TestClient) -> None:
    resp = client.get("/")
    assert "/static/fonts/SourceSans3-Regular.woff2" in resp.text
    assert "fonts.googleapis.com" not in resp.text
