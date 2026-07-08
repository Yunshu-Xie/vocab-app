"""Unit tests for the tokenization and phrase-locating service."""

from __future__ import annotations

from app.services.tokenize import find_phrase_range, tokenize


def test_tokenize_rebuilds_sentence():
    sentence = "The ubiquitous smartphone has transformed how we communicate."
    tokens = tokenize(sentence)
    assert "".join(t.text for t in tokens) == sentence


def test_find_phrase_range_single_word():
    tokens = tokenize("The ubiquitous smartphone is everywhere.")
    rng = find_phrase_range(tokens, "ubiquitous")
    assert rng is not None
    start, end = rng
    assert tokens[start].text == tokens[end].text == "ubiquitous"


def test_find_phrase_range_multi_word_phrase():
    tokens = tokenize("Please don't give up on your dreams.")
    rng = find_phrase_range(tokens, "give up")
    assert rng is not None
    start, end = rng
    span = "".join(t.text for t in tokens[start : end + 1])
    assert span == "give up"


def test_find_phrase_range_case_insensitive():
    tokens = tokenize("In spite of the rain, we went out.")
    rng = find_phrase_range(tokens, "In Spite Of")
    assert rng is not None
    start, end = rng
    span = "".join(t.text for t in tokens[start : end + 1]).lower()
    assert span == "in spite of"


def test_find_phrase_range_not_found_returns_none():
    tokens = tokenize("She looked forward to the trip.")
    assert find_phrase_range(tokens, "give up") is None


def test_find_phrase_range_empty_phrase_returns_none():
    tokens = tokenize("Hello world.")
    assert find_phrase_range(tokens, "!!!") is None
