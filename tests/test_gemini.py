"""Tests for the gemini service wrapper. The SDK client is mocked."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

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
        with pytest.raises(gemini.GeminiError):
            gemini.translate_sentence("Hi.")


def test_invalid_json_raises():
    client = MagicMock()
    client.models.generate_content.return_value = MagicMock(text="not json {{{")
    with patch.object(gemini, "_get_client", return_value=client):
        with pytest.raises(gemini.GeminiError):
            gemini.translate_sentence("Hi.")


def test_missing_api_key_raises(monkeypatch):
    monkeypatch.setattr(gemini.settings, "gemini_api_key", "")
    monkeypatch.setattr(gemini, "_client", None)
    with pytest.raises(gemini.GeminiError, match="GEMINI_API_KEY"):
        gemini.translate_sentence("Hi.")


def test_sdk_exception_wrapped():
    client = MagicMock()
    client.models.generate_content.side_effect = RuntimeError("network down")
    with patch.object(gemini, "_get_client", return_value=client):
        with pytest.raises(gemini.GeminiError, match="network down"):
            gemini.translate_sentence("Hi.")
