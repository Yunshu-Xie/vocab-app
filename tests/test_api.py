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


_FAKE_TRANSLATE_WITH_PHRASE = {
    "translation": "尽管下雨了，他们还是放弃了。",
    "key_words": [
        {
            "word": "give up",
            "lemma": "give up",
            "pos": "phrasal verb",
            "meaning_in_context": "放弃了",
            "general_meaning": "放弃",
            "example": "Never give up on your dreams.",
            "difficulty": "B1",
        },
        {
            "word": "In spite of",
            "lemma": "in spite of",
            "pos": "collocation",
            "meaning_in_context": "尽管",
            "general_meaning": "尽管，不顾",
            "example": "In spite of the cold, she went out.",
            "difficulty": "B2",
        },
    ],
}


@patch("app.routers.translate.translate_sentence", return_value=_FAKE_TRANSLATE_WITH_PHRASE)
def test_translate_locates_phrase_key_words(_mock, client):
    resp = client.post(
        "/api/translate",
        json={"sentence": "In spite of the rain, they decided to give up."},
    )
    assert resp.status_code == 200
    data = resp.json()
    key_words = {kw["word"]: kw for kw in data["key_words"]}

    give_up = key_words["give up"]
    assert give_up["start_idx"] is not None and give_up["end_idx"] is not None
    span = "".join(
        t["text"] for t in data["tokens"][give_up["start_idx"] : give_up["end_idx"] + 1]
    )
    assert span == "give up"

    in_spite_of = key_words["In spite of"]
    assert in_spite_of["start_idx"] is not None and in_spite_of["end_idx"] is not None
    span = "".join(
        t["text"]
        for t in data["tokens"][in_spite_of["start_idx"] : in_spite_of["end_idx"] + 1]
    )
    assert span.lower() == "in spite of"


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


def test_vocab_duplicate_merges_as_new_usage(client):
    first = client.post("/api/vocab", json=_vocab_payload())
    assert first.status_code == 201
    vid = first.json()["id"]
    assert len(first.json()["usages"]) == 1

    resp = client.post(
        "/api/vocab",
        json=_vocab_payload(source_sentence="A different sentence with ubiquitous."),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == vid
    assert len(data["usages"]) == 2
    assert data["usages"][1]["source_sentence"] == "A different sentence with ubiquitous."


def test_vocab_duplicate_same_sentence_does_not_duplicate_usage(client):
    client.post("/api/vocab", json=_vocab_payload())
    resp = client.post("/api/vocab", json=_vocab_payload())
    assert resp.status_code == 200
    assert len(resp.json()["usages"]) == 1


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
