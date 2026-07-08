"""Unit tests for tokenization and phrase-locating helpers."""

from __future__ import annotations

from app.routers.translate import _find_phrase_range, _tokenize


def test_tokenize_rebuilds_sentence():
    sentence = "The ubiquitous smartphone has transformed how we communicate."
    tokens = _tokenize(sentence)
    assert "".join(t.text for t in tokens) == sentence


def test_find_phrase_range_single_word():
    tokens = _tokenize("The ubiquitous smartphone is everywhere.")
    rng = _find_phrase_range(tokens, "ubiquitous")
    assert rng is not None
    start, end = rng
    assert tokens[start].text == tokens[end].text == "ubiquitous"


def test_find_phrase_range_multi_word_phrase():
    tokens = _tokenize("Please don't give up on your dreams.")
    rng = _find_phrase_range(tokens, "give up")
    assert rng is not None
    start, end = rng
    span = "".join(t.text for t in tokens[start : end + 1])
    assert span == "give up"


def test_find_phrase_range_case_insensitive():
    tokens = _tokenize("In spite of the rain, we went out.")
    rng = _find_phrase_range(tokens, "In Spite Of")
    assert rng is not None
    start, end = rng
    span = "".join(t.text for t in tokens[start : end + 1]).lower()
    assert span == "in spite of"


def test_find_phrase_range_not_found_returns_none():
    tokens = _tokenize("She looked forward to the trip.")
    assert _find_phrase_range(tokens, "give up") is None


def test_find_phrase_range_empty_phrase_returns_none():
    tokens = _tokenize("Hello world.")
    assert _find_phrase_range(tokens, "!!!") is None
