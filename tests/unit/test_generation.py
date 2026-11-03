"""Tests for AI generation module — uses a stubbed Anthropic client (no live API calls)."""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ── Shared fixtures and helpers ───────────────────────────────────────────────

def _make_usage(input_tokens=1000, output_tokens=500):
    usage = MagicMock()
    usage.input_tokens = input_tokens
    usage.output_tokens = output_tokens
    return usage


def _make_response(questions: list[dict], input_tokens=1000, output_tokens=500):
    """Build a fake anthropic.Anthropic().messages.create() return value."""
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = json.dumps(questions)

    response = MagicMock()
    response.content = [text_block]
    response.usage = _make_usage(input_tokens, output_tokens)
    return response


_VALID_QUESTION = {
    "difficulty": "Easy",
    "type": "mcq",
    "question": "What is 2 + 2?",
    "options": ["2", "3", "4", "5"],
    "answer": 2,
    "explanation": "2 + 2 equals 4.",
    "source_quote": "",
}

_VALID_MATHS_Q = {
    "difficulty": "Medium",
    "type": "mcq",
    "question": "A car travels 60 km in 1 hour. What is its speed?",
    "options": ["30 km/h", "60 km/h", "120 km/h", "15 km/h"],
    "answer": 1,
    "explanation": (
        "Given: distance = 60 km, time = 1 h\n"
        "Formula: speed = distance / time\n"
        "Substitution: speed = 60 / 1\n"
        "Answer: 60 km/h"
    ),
    "source_quote": "",
}


# ── Unit tests for generate_questions() ──────────────────────────────────────

@patch("medhabhyasah.generation.anthropic.Anthropic")
@patch("medhabhyasah.credentials.keyring")
def test_generate_questions_returns_result(mock_kr, MockAnthropic):
    mock_kr.get_password = MagicMock(return_value="sk-ant-test")
    mock_client = MagicMock()
    MockAnthropic.return_value = mock_client
    mock_client.messages.create.return_value = _make_response([_VALID_QUESTION] * 5)

    from medhabhyasah.generation import generate_questions
    result = generate_questions("Maths", "Algebra", "9", "CBSE", "", 5)

    assert len(result.questions) == 5
    assert result.questions[0]["question"] == _VALID_QUESTION["question"]


@patch("medhabhyasah.generation.anthropic.Anthropic")
@patch("medhabhyasah.credentials.keyring")
def test_generate_questions_cost_calculation(mock_kr, MockAnthropic):
    mock_kr.get_password = MagicMock(return_value="sk-ant-test")
    mock_client = MagicMock()
    MockAnthropic.return_value = mock_client
    # 1M input tokens → $4.00, 1M output tokens → $20.00
    mock_client.messages.create.return_value = _make_response(
        [_VALID_QUESTION], input_tokens=1_000_000, output_tokens=1_000_000
    )

    from medhabhyasah.generation import generate_questions
    result = generate_questions("Science", "Cells", "7", "CBSE", "", 1)

    assert abs(result.api_cost_usd - 24.00) < 0.001


@patch("medhabhyasah.generation.anthropic.Anthropic")
@patch("medhabhyasah.credentials.keyring")
def test_generate_questions_small_cost(mock_kr, MockAnthropic):
    mock_kr.get_password = MagicMock(return_value="sk-ant-test")
    mock_client = MagicMock()
    MockAnthropic.return_value = mock_client
    # 500 input tokens, 1000 output tokens
    mock_client.messages.create.return_value = _make_response(
        [_VALID_QUESTION], input_tokens=500, output_tokens=1000
    )

    from medhabhyasah.generation import generate_questions
    result = generate_questions("English", "Grammar", "6", "CBSE", "", 1)

    expected = (500 / 1_000_000) * 4.00 + (1000 / 1_000_000) * 20.00
    assert abs(result.api_cost_usd - expected) < 1e-9


@patch("medhabhyasah.credentials.keyring")
def test_generate_questions_no_api_key_raises(mock_kr):
    mock_kr.get_password = MagicMock(return_value=None)

    from medhabhyasah.generation import generate_questions
    with pytest.raises(RuntimeError, match="API key"):
        generate_questions("Maths", "Algebra", "9", "CBSE", "", 5)


@patch("medhabhyasah.generation.anthropic.Anthropic")
@patch("medhabhyasah.credentials.keyring")
def test_generate_questions_calls_with_system_prompt(mock_kr, MockAnthropic):
    mock_kr.get_password = MagicMock(return_value="sk-ant-test")
    mock_client = MagicMock()
    MockAnthropic.return_value = mock_client
    mock_client.messages.create.return_value = _make_response([_VALID_QUESTION])

    from medhabhyasah.generation import generate_questions
    generate_questions("Maths", "Fractions", "7", "CBSE", "", 1)

    call_kwargs = mock_client.messages.create.call_args[1]
    assert "system" in call_kwargs
    assert "JSON" in call_kwargs["system"] or "json" in call_kwargs["system"].lower() or "question" in call_kwargs["system"].lower()


# ── API route tests (stubbed Anthropic + keyring) ────────────────────────────

@pytest.fixture()
def authed_client(tmp_path: Path):
    from medhabhyasah.api import create_app
    app = create_app(db_path=tmp_path / "test.db")
    c = TestClient(app)
    with patch("medhabhyasah.credentials.keyring") as mock_kr:
        mock_kr.get_password = MagicMock(return_value="1234")
        mock_kr.set_password = MagicMock()
        yield c, mock_kr


def _create_req(c, mock_kr, subject="Maths", topic="Fractions", count=5):
    mock_kr.get_password = MagicMock(return_value="1234")
    r = c.post(
        "/api/parent/generation-requests",
        json={"subject": subject, "topic": topic, "grade": "7", "exam": "CBSE", "question_count": count},
        headers={"X-Parent-Pin": "1234"},
    )
    assert r.status_code == 200
    return r.json()["id"]


def _parse_sse_done(response) -> dict:
    """Extract the 'done' event from an SSE response."""
    for line in response.text.strip().split("\n"):
        line = line.strip()
        if not line.startswith("data: "):
            continue
        data = json.loads(line[6:])
        if data.get("step") == "done":
            return data
    raise AssertionError("No 'done' SSE event found in response")


def _dual_keyring_mock(pin="1234", api_key="sk-ant-test"):
    """Return a keyring mock that serves PIN and API key from separate user slots."""
    mock_kr = MagicMock()

    def _get(service, user):
        if user == "parent-pin":
            return pin
        if user == "anthropic-api-key":
            return api_key
        return None

    mock_kr.get_password = MagicMock(side_effect=_get)
    mock_kr.set_password = MagicMock()
    return mock_kr


def test_generate_route_stores_questions_and_cost(tmp_path: Path):
    from medhabhyasah.api import create_app
    app = create_app(db_path=tmp_path / "test.db")
    c = TestClient(app)

    questions = [dict(_VALID_MATHS_Q) for _ in range(5)]
    with (
        patch("medhabhyasah.generation.anthropic.Anthropic") as MockAnthropic,
        patch("medhabhyasah.credentials.keyring", _dual_keyring_mock()),
    ):
        mock_client = MagicMock()
        MockAnthropic.return_value = mock_client
        mock_client.messages.create.return_value = _make_response(
            questions, input_tokens=2000, output_tokens=3000
        )

        r_create = c.post(
            "/api/parent/generation-requests",
            json={"subject": "Maths", "topic": "Fractions", "grade": "7",
                  "exam": "CBSE", "question_count": 5},
            headers={"X-Parent-Pin": "1234"},
        )
        assert r_create.status_code == 200
        req_id = r_create.json()["id"]

        r = c.post(
            f"/api/parent/generation-requests/{req_id}/generate",
            headers={"X-Parent-Pin": "1234"},
        )

    assert r.status_code == 200
    body = _parse_sse_done(r)
    assert body["question_count"] == 5
    assert body["auto_checked"] == 5
    assert body["draft"] == 0
    assert body["api_cost_usd"] > 0


def test_generate_route_marks_complete_with_cost(tmp_path: Path):
    from medhabhyasah.api import create_app
    app = create_app(db_path=tmp_path / "test.db")
    c = TestClient(app)

    with (
        patch("medhabhyasah.generation.anthropic.Anthropic") as MockAnthropic,
        patch("medhabhyasah.credentials.keyring", _dual_keyring_mock()),
    ):
        mock_client = MagicMock()
        MockAnthropic.return_value = mock_client
        mock_client.messages.create.return_value = _make_response(
            [_VALID_MATHS_Q] * 3, input_tokens=1000, output_tokens=500
        )

        r_create = c.post(
            "/api/parent/generation-requests",
            json={"subject": "Maths", "topic": "Speed", "grade": "7",
                  "exam": "CBSE", "question_count": 3},
            headers={"X-Parent-Pin": "1234"},
        )
        req_id = r_create.json()["id"]

        c.post(
            f"/api/parent/generation-requests/{req_id}/generate",
            headers={"X-Parent-Pin": "1234"},
        )
        r2 = c.get(
            "/api/parent/generation-requests",
            headers={"X-Parent-Pin": "1234"},
        )

    reqs = r2.json()
    req = next(r for r in reqs if r["id"] == req_id)
    assert req["status"] == "complete"
    assert req["api_cost_usd"] is not None


def test_generate_route_already_complete_returns_400(tmp_path: Path):
    from medhabhyasah.api import create_app
    app = create_app(db_path=tmp_path / "test.db")
    c = TestClient(app)

    with (
        patch("medhabhyasah.generation.anthropic.Anthropic") as MockAnthropic,
        patch("medhabhyasah.credentials.keyring", _dual_keyring_mock()),
    ):
        mock_client = MagicMock()
        MockAnthropic.return_value = mock_client
        mock_client.messages.create.return_value = _make_response([_VALID_MATHS_Q])

        r_create = c.post(
            "/api/parent/generation-requests",
            json={"subject": "Maths", "topic": "Algebra", "grade": "9",
                  "exam": "CBSE", "question_count": 1},
            headers={"X-Parent-Pin": "1234"},
        )
        req_id = r_create.json()["id"]

        c.post(f"/api/parent/generation-requests/{req_id}/generate",
               headers={"X-Parent-Pin": "1234"})
        r2 = c.post(f"/api/parent/generation-requests/{req_id}/generate",
                    headers={"X-Parent-Pin": "1234"})

    assert r2.status_code == 400


def test_generate_route_404_for_missing_request(tmp_path: Path):
    from medhabhyasah.api import create_app
    app = create_app(db_path=tmp_path / "test.db")
    c = TestClient(app)

    with patch("medhabhyasah.credentials.keyring", _dual_keyring_mock()):
        r = c.post(
            "/api/parent/generation-requests/9999/generate",
            headers={"X-Parent-Pin": "1234"},
        )
    assert r.status_code == 404


# ── Gemini dispatch tests ─────────────────────────────────────────────────────

def _dual_keyring_mock_gemini(pin="1234", api_key="AIzaFakeGeminiKey"):
    """Keyring mock that routes to the Gemini key slot."""
    mock_kr = MagicMock()

    def _get(service, user):
        if user == "parent-pin":
            return pin
        if user == "gemini-api-key":
            return api_key
        return None

    mock_kr.get_password = MagicMock(side_effect=_get)
    mock_kr.set_password = MagicMock()
    return mock_kr


def _make_gemini_response(questions: list[dict], input_tokens=1000, output_tokens=500):
    """Build a fake google.genai generate_content() return value."""
    import json as _json
    response = MagicMock()
    response.text = _json.dumps(questions)
    usage = MagicMock()
    usage.prompt_token_count = input_tokens
    usage.candidates_token_count = output_tokens
    response.usage_metadata = usage
    return response


@patch("medhabhyasah.credentials.keyring")
def test_generate_questions_gemini_dispatch(mock_kr):
    mock_kr.get_password = MagicMock(side_effect=lambda s, u: (
        "AIzaFakeGeminiKey" if u == "gemini-api-key" else None
    ))

    mock_response = _make_gemini_response([_VALID_QUESTION] * 3)
    mock_models = MagicMock()
    mock_models.generate_content.return_value = mock_response
    mock_client = MagicMock()
    mock_client.models = mock_models
    mock_genai = MagicMock()
    mock_genai.Client.return_value = mock_client
    mock_genai_types = MagicMock()

    with patch.dict("sys.modules", {
        "google": MagicMock(genai=mock_genai),
        "google.genai": mock_genai,
        "google.genai.types": mock_genai_types,
    }):
        from medhabhyasah.generation import generate_questions
        result = generate_questions("Maths", "Algebra", "9", "CBSE", "", 3)

    assert len(result.questions) == 3
    mock_models.generate_content.assert_called_once()


@patch("medhabhyasah.credentials.keyring")
def test_generate_questions_gemini_cost_calculation(mock_kr):
    mock_kr.get_password = MagicMock(side_effect=lambda s, u: (
        "AIzaFakeGeminiKey" if u == "gemini-api-key" else None
    ))

    # 1M input → $0.10, 1M output → $0.40 → total $0.50
    mock_response = _make_gemini_response([_VALID_QUESTION], input_tokens=1_000_000, output_tokens=1_000_000)
    mock_models = MagicMock()
    mock_models.generate_content.return_value = mock_response
    mock_client = MagicMock()
    mock_client.models = mock_models
    mock_genai = MagicMock()
    mock_genai.Client.return_value = mock_client
    mock_genai_types = MagicMock()

    with patch.dict("sys.modules", {
        "google": MagicMock(genai=mock_genai),
        "google.genai": mock_genai,
        "google.genai.types": mock_genai_types,
    }):
        from medhabhyasah.generation import generate_questions
        result = generate_questions("Science", "Cells", "7", "CBSE", "", 1)

    assert abs(result.api_cost_usd - 0.50) < 0.001


@patch("medhabhyasah.credentials.keyring")
def test_generate_questions_no_key_raises(mock_kr):
    mock_kr.get_password = MagicMock(return_value=None)

    from medhabhyasah.generation import generate_questions
    with pytest.raises(RuntimeError, match="No API key"):
        generate_questions("Maths", "Algebra", "9", "CBSE", "", 5)
