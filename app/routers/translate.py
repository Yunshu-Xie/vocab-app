"""Translate sentence + per-word lookup endpoints."""

from __future__ import annotations

import asyncio
import re

from fastapi import APIRouter, HTTPException

from app.models.schemas import (
    KeyWord,
    LookupRequest,
    Token,
    TranslateRequest,
    TranslateResponse,
)
from app.services.gemini import GeminiError, lookup_word, translate_sentence

router = APIRouter()

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'-]*|[^A-Za-z]+")


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


@router.post("/translate", response_model=TranslateResponse)
async def translate(req: TranslateRequest) -> TranslateResponse:
    try:
        data = await asyncio.to_thread(translate_sentence, req.sentence)
    except GeminiError as exc:
        raise HTTPException(502, str(exc)) from exc

    return TranslateResponse(
        translation=data["translation"],
        tokens=_tokenize(req.sentence),
        key_words=[KeyWord(**kw) for kw in data["key_words"]],
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
