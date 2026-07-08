"""Translate sentence + per-word lookup endpoints."""

from __future__ import annotations

import asyncio
import re

from fastapi import APIRouter, HTTPException

from app.models.schemas import (
    KeyWord,
    LookupRequest,
    Token,
    TranslatedKeyWord,
    TranslateRequest,
    TranslateResponse,
)
from app.services.gemini import GeminiError, lookup_word, translate_sentence

router = APIRouter()

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'-]*|[^A-Za-z]+")
_PHRASE_WORD_RE = re.compile(r"[A-Za-z'-]+")


def _tokenize(sentence: str) -> list[Token]:
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


def _find_phrase_range(tokens: list[Token], phrase: str) -> tuple[int, int] | None:
    """Locate `phrase` (1+ words) as a contiguous run of word-tokens.

    Returns the (start, end) inclusive index range into `tokens`, or None if
    the phrase's words don't appear in that exact order (e.g. Gemini
    paraphrased it instead of quoting the sentence verbatim).
    """
    words = [w.lower() for w in _PHRASE_WORD_RE.findall(phrase)]
    if not words:
        return None
    word_positions = [i for i, t in enumerate(tokens) if t.is_word]
    n = len(words)
    for start in range(len(word_positions) - n + 1):
        idxs = word_positions[start : start + n]
        if all(tokens[idxs[k]].lower == words[k] for k in range(n)):
            return idxs[0], idxs[-1]
    return None


@router.post("/translate", response_model=TranslateResponse)
async def translate(req: TranslateRequest) -> TranslateResponse:
    try:
        data = await asyncio.to_thread(translate_sentence, req.sentence)
    except GeminiError as exc:
        raise HTTPException(502, str(exc)) from exc

    tokens = _tokenize(req.sentence)
    key_words = []
    for kw in data["key_words"]:
        rng = _find_phrase_range(tokens, kw["word"])
        start_idx, end_idx = rng if rng else (None, None)
        key_words.append(TranslatedKeyWord(**kw, start_idx=start_idx, end_idx=end_idx))

    return TranslateResponse(
        translation=data["translation"],
        tokens=tokens,
        key_words=key_words,
    )


@router.post("/lookup", response_model=KeyWord)
async def lookup(req: LookupRequest) -> KeyWord:
    try:
        data = await asyncio.to_thread(
            lookup_word, req.word, req.sentence, req.translation
        )
    except GeminiError as exc:
        raise HTTPException(502, str(exc)) from exc

    return KeyWord(**data)
