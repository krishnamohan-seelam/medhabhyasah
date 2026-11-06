"""Known failure kinds map to fixed plain messages."""
import json
from unittest.mock import MagicMock, patch

import anthropic
import httpx
import pytest


def _status_error(cls, status, text="boom"):
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    return cls(text, response=httpx.Response(status, request=request), body=None)


_REQ = httpx.Request("POST", "https://api.anthropic.com/v1/messages")

_CASES = [
    (anthropic.APITimeoutError(request=_REQ), "timeout"),
    (anthropic.APIConnectionError(request=_REQ), "network"),
    (ConnectionError("no route"), "network"),
    (_status_error(anthropic.RateLimitError, 429), "rate_limit"),
    (_status_error(anthropic.InternalServerError, 500), "outage"),
    (_status_error(anthropic.InternalServerError, 529, "overloaded"), "outage"),
    (_status_error(anthropic.BadRequestError, 400, "Your credit balance is too low"), "billing"),
    (json.JSONDecodeError("bad", "x", 0), "bad_output"),
    (ValueError("Anthropic API did not return a JSON array"), "bad_output"),
    (RuntimeError("something odd"), "unknown"),
]


@pytest.mark.parametrize("error,kind", _CASES)
def test_error_maps_to_kind_with_fixed_message(error, kind):
    kr = MagicMock()
    kr.get_password = MagicMock(return_value="sk-ant-test")
    with patch("medhabhyasah.generation.anthropic.Anthropic") as MockA, \
            patch("medhabhyasah.credentials.keyring", kr):
        MockA.return_value.messages.create.side_effect = error
        from medhabhyasah.generation import _FAILURE_MESSAGES, GenerationFailure, generate_questions
        with pytest.raises(GenerationFailure) as info:
            generate_questions("Maths", "Algebra", "9", "CBSE", "", 1)
    assert info.value.kind == kind
    assert str(info.value) == _FAILURE_MESSAGES[kind]


def test_missing_key_message_is_ours():
    kr = MagicMock()
    kr.get_password = MagicMock(return_value=None)
    with patch("medhabhyasah.credentials.keyring", kr):
        from medhabhyasah.generation import GenerationFailure, generate_questions
        with pytest.raises(GenerationFailure) as info:
            generate_questions("Maths", "Algebra", "9", "CBSE", "", 1)
    assert info.value.kind == "no_key"
