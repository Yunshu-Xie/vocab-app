"""Sentence tokenization and phrase locating — deterministic text logic, no LLM."""

from __future__ import annotations

import re

from app.models.schemas import Token

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'-]*|[^A-Za-z]+")


def tokenize(sentence: str) -> list[Token]:
    tokens: list[Token] = []
    for chunk in _WORD_RE.findall(sentence):
        is_word = bool(chunk) and chunk[0].isalpha()
        tokens.append(
            Token(
                text=chunk,
                is_word=is_word,
                lower=chunk.lower() if is_word else None,
            )
        )
    return tokens


def find_phrase_range(tokens: list[Token], phrase: str) -> tuple[int, int] | None:
    """Locate `phrase` (1+ words) as a contiguous run of word-tokens.

    Returns the (start, end) inclusive index range into `tokens`, or None if
    the phrase's words don't appear in that exact order (e.g. Gemini
    paraphrased it instead of quoting the sentence verbatim).
    """
    words = [t.lower for t in tokenize(phrase) if t.is_word]
    if not words:
        return None
    word_positions = [i for i, t in enumerate(tokens) if t.is_word]
    n = len(words)
    for start in range(len(word_positions) - n + 1):
        idxs = word_positions[start : start + n]
        if all(tokens[idxs[k]].lower == words[k] for k in range(n)):
            return idxs[0], idxs[-1]
    return None
