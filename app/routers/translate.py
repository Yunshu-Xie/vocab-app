"""Translate sentence + per-word lookup endpoints."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException

from app.models.schemas import (
    KeyWord,
    LookupRequest,
    TranslatedKeyWord,
    TranslateRequest,
    TranslateResponse,
)
from app.services.gemini import GeminiError, lookup_word, translate_sentence
from app.services.tokenize import find_phrase_range, tokenize

router = APIRouter()


def _gemini_http_error(exc: GeminiError) -> HTTPException:
    return HTTPException(502, {"message": str(exc), "retryable": exc.retryable})


@router.post("/translate", response_model=TranslateResponse)
async def translate(req: TranslateRequest) -> TranslateResponse:
    try:
        data = await asyncio.to_thread(translate_sentence, req.sentence)
    except GeminiError as exc:
        raise _gemini_http_error(exc) from exc

    tokens = tokenize(req.sentence)
    key_words = []
    for kw in data["key_words"]:
        rng = find_phrase_range(tokens, kw["word"])
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
        raise _gemini_http_error(exc) from exc

    return KeyWord(**data)
