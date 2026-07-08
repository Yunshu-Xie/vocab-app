"""Tests for the gemini service wrapper. The SDK client is mocked."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from google.genai.errors import ClientError, ServerError

from app.services import gemini


@pytest.fixture(autouse=True)
def _reset_client(monkeypatch):
    """Each test sees a fresh module-level client and an API key set."""
    monkeypatch.setattr(gemini, "_client", None)
    monkeypatch.setattr(gemini.settings, "gemini_api_key", "test-key")
    yield


def _mock_response(payload: dict) -> MagicMock:
    resp = MagicMock()
    resp.text = json.dumps(payload, ensure_ascii=False)
    return resp


def _patched_client(payload: dict) -> MagicMock:
    client = MagicMock()
    client.models.generate_content.return_value = _mock_response(payload)
    return client


def test_translate_returns_parsed_dict():
    payload = {
        "translation": "你好世界",
        "key_words": [
            {
                "word": "Hello",
                "lemma": "hello",
                "pos": "interjection",
                "meaning_in_context": "问候",
                "general_meaning": "你好",
                "example": "Hello, friend!",
                "difficulty": "A1",
            }
        ],
    }
    with patch.object(gemini, "_get_client", return_value=_patched_client(payload)):
        result = gemini.translate_sentence("Hello world.")
    assert result["translation"] == "你好世界"
    assert result["key_words"][0]["word"] == "Hello"


def test_lookup_returns_keyword_dict():
    payload = {
        "word": "smartphone",
        "lemma": "smartphone",
        "pos": "noun",
        "meaning_in_context": "智能手机",
        "general_meaning": "智能手机",
        "example": "Where is my smartphone?",
        "difficulty": "A2",
    }
    with patch.object(gemini, "_get_client", return_value=_patched_client(payload)):
        result = gemini.lookup_word("smartphone", "I lost my smartphone.", "我丢了手机")
    assert result["word"] == "smartphone"
    assert result["difficulty"] == "A2"


def test_empty_response_raises():
    client = MagicMock()
    client.models.generate_content.return_value = MagicMock(text="")
    with patch.object(gemini, "_get_client", return_value=client):
        with pytest.raises(gemini.GeminiError) as exc:
            gemini.translate_sentence("Hi.")
    assert exc.value.retryable is True


def test_invalid_json_raises():
    client = MagicMock()
    client.models.generate_content.return_value = MagicMock(text="not json {{{")
    with patch.object(gemini, "_get_client", return_value=client):
        with pytest.raises(gemini.GeminiError) as exc:
            gemini.translate_sentence("Hi.")
    assert exc.value.retryable is True


def test_missing_api_key_raises(monkeypatch):
    monkeypatch.setattr(gemini.settings, "gemini_api_key", "")
    monkeypatch.setattr(gemini, "_client", None)
    with pytest.raises(gemini.GeminiError, match="GEMINI_API_KEY") as exc:
        gemini.translate_sentence("Hi.")
    assert exc.value.retryable is False


def test_sdk_exception_wrapped_without_leaking_raw_text():
    """A bare (non-APIError) exception gets a fixed, retryable message —
    the original exception text must not reach the user-facing message."""
    client = MagicMock()
    client.models.generate_content.side_effect = RuntimeError("network down: 10.0.0.1:443 refused")
    with patch.object(gemini, "_get_client", return_value=client):
        with pytest.raises(gemini.GeminiError) as exc:
            gemini.translate_sentence("Hi.")
    assert "10.0.0.1" not in str(exc.value)
    assert exc.value.retryable is True


@pytest.mark.parametrize(
    "error, expect_retryable",
    [
        (
            ServerError(
                503, {"error": {"code": 503, "message": "overloaded", "status": "UNAVAILABLE"}}
            ),
            True,
        ),
        (
            ClientError(
                429, {"error": {"code": 429, "message": "quota", "status": "RESOURCE_EXHAUSTED"}}
            ),
            False,
        ),
        (
            ClientError(
                403, {"error": {"code": 403, "message": "denied", "status": "PERMISSION_DENIED"}}
            ),
            False,
        ),
        (
            ClientError(
                400, {"error": {"code": 400, "message": "bad", "status": "INVALID_ARGUMENT"}}
            ),
            False,
        ),
    ],
)
def test_api_error_classified_without_leaking_raw_text(error, expect_retryable):
    client = MagicMock()
    client.models.generate_content.side_effect = error
    with patch.object(gemini, "_get_client", return_value=client):
        with pytest.raises(gemini.GeminiError) as exc:
            gemini.translate_sentence("Hi.")
    assert exc.value.retryable is expect_retryable
    # The raw upstream status/message must not leak into the user-facing text.
    assert "UNAVAILABLE" not in str(exc.value)
    assert "RESOURCE_EXHAUSTED" not in str(exc.value)
