"""Integration tests for API endpoints. Gemini service is mocked."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.gemini import GeminiError


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


_FAKE_TRANSLATE = {
    "translation": "无处不在的智能手机改变了通讯。",
    "key_words": [
        {
            "word": "ubiquitous",
            "lemma": "ubiquitous",
            "pos": "adjective",
            "meaning_in_context": "本句指智能手机无处不在",
            "general_meaning": "无处不在的",
            "example": "Plastic is ubiquitous in oceans.",
            "difficulty": "B2",
        },
        {
            "word": "revolutionized",
            "lemma": "revolutionize",
            "pos": "verb",
            "meaning_in_context": "彻底改变了",
            "general_meaning": "使发生革命性变化",
            "example": "The internet revolutionized business.",
            "difficulty": "B2",
        },
    ],
}

_FAKE_LOOKUP = {
    "word": "smartphone",
    "lemma": "smartphone",
    "pos": "noun",
    "meaning_in_context": "智能手机",
    "general_meaning": "智能手机",
    "example": "I left my smartphone at home.",
    "difficulty": "A2",
}


@patch("app.routers.translate.translate_sentence", return_value=_FAKE_TRANSLATE)
def test_translate_success(_mock, client):
    resp = client.post(
        "/api/translate",
        json={"sentence": "The ubiquitous smartphone has revolutionized communication."},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["translation"] == _FAKE_TRANSLATE["translation"]
    assert len(data["key_words"]) == 2
    assert any(t["text"] == "ubiquitous" and t["is_word"] for t in data["tokens"])
    # Tokens should preserve the original sentence
    rebuilt = "".join(t["text"] for t in data["tokens"])
    assert rebuilt == "The ubiquitous smartphone has revolutionized communication."


def test_translate_empty_returns_422(client):
    resp = client.post("/api/translate", json={"sentence": ""})
    assert resp.status_code == 422


@patch(
    "app.routers.translate.translate_sentence",
    side_effect=GeminiError("API quota exceeded"),
)
def test_translate_gemini_error_returns_502(_mock, client):
    resp = client.post("/api/translate", json={"sentence": "Hello world"})
    assert resp.status_code == 502
    assert "quota" in resp.json()["detail"]


@patch("app.routers.translate.lookup_word", return_value=_FAKE_LOOKUP)
def test_lookup_success(_mock, client):
    resp = client.post(
        "/api/lookup",
        json={
            "word": "smartphone",
            "sentence": "The smartphone is useful.",
            "translation": "智能手机很有用。",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["word"] == "smartphone"
    assert data["difficulty"] == "A2"


def _vocab_payload(**overrides) -> dict:
    base = {
        "word": "ubiquitous",
        "lemma": "ubiquitous",
        "pos": "adjective",
        "meaning": "无处不在的",
        "example": "It's ubiquitous.",
        "source_sentence": "The ubiquitous smartphone...",
        "source_translation": "无处不在的手机……",
        "notes": "",
    }
    base.update(overrides)
    return base


def test_vocab_crud_flow(client):
    # Create
    resp = client.post("/api/vocab", json=_vocab_payload())
    assert resp.status_code == 201
    row = resp.json()
    vid = row["id"]
    assert row["word"] == "ubiquitous"

    # List
    resp = client.get("/api/vocab")
    assert resp.status_code == 200
    listing = resp.json()
    assert listing["total"] == 1

    # Get one
    resp = client.get(f"/api/vocab/{vid}")
    assert resp.status_code == 200
    assert resp.json()["id"] == vid

    # Update
    resp = client.put(f"/api/vocab/{vid}", json={"notes": "记一下"})
    assert resp.status_code == 200
    assert resp.json()["notes"] == "记一下"

    # Delete
    resp = client.delete(f"/api/vocab/{vid}")
    assert resp.status_code == 204

    # Gone
    resp = client.get(f"/api/vocab/{vid}")
    assert resp.status_code == 404


def test_vocab_duplicate_returns_409(client):
    client.post("/api/vocab", json=_vocab_payload())
    resp = client.post("/api/vocab", json=_vocab_payload())
    assert resp.status_code == 409
    detail = resp.json()["detail"]
    # Detail comes through as a dict (we pass dict to HTTPException)
    assert isinstance(detail, dict)
    assert detail["message"] == "已在单词本中"
    assert detail["existing_id"] > 0


def test_vocab_search(client):
    client.post(
        "/api/vocab",
        json=_vocab_payload(word="ubiquitous", lemma="ubiquitous", pos="adjective"),
    )
    client.post(
        "/api/vocab",
        json=_vocab_payload(
            word="ephemeral", lemma="ephemeral", pos="adjective", meaning="短暂的"
        ),
    )

    resp = client.get("/api/vocab", params={"q": "ubiq"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["word"] == "ubiquitous"


def test_vocab_update_missing_returns_404(client):
    resp = client.put("/api/vocab/9999", json={"notes": "x"})
    assert resp.status_code == 404


def test_root_serves_html(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    assert "英语单词查背一体" in resp.text
