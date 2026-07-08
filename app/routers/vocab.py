"""Vocabulary notebook CRUD endpoints."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Query, Response

from app.models.schemas import (
    VocabCreate,
    VocabListResponse,
    VocabResponse,
    VocabUpdate,
)
from app.services import db

router = APIRouter()


@router.post("/vocab", response_model=VocabResponse, status_code=201)
async def create_vocab(payload: VocabCreate, response: Response) -> VocabResponse:
    try:
        row = await asyncio.to_thread(insert_or_raise, payload.model_dump())
    except db.DuplicateVocabError as exc:
        # Meeting a known word/phrase again isn't an error worth blocking on —
        # record this sentence as another usage instead of rejecting it.
        row = await asyncio.to_thread(
            db.add_vocab_usage,
            exc.existing_id,
            payload.source_sentence,
            payload.source_translation,
        )
        response.status_code = 200
    return VocabResponse(**row)


def insert_or_raise(data: dict) -> dict:
    """Thin wrapper so we can `to_thread(insert_or_raise, data)` and catch in caller."""
    return db.insert_vocab(data)


@router.get("/vocab", response_model=VocabListResponse)
async def list_vocab_endpoint(
    q: str = Query("", max_length=100),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
) -> VocabListResponse:
    items, total = await asyncio.to_thread(db.list_vocab, q, page, limit)
    return VocabListResponse(
        items=[VocabResponse(**r) for r in items],
        total=total,
        page=page,
        limit=limit,
    )


@router.get("/vocab/{vocab_id}", response_model=VocabResponse)
async def get_vocab_endpoint(vocab_id: int) -> VocabResponse:
    row = await asyncio.to_thread(db.get_vocab, vocab_id)
    if row is None:
        raise HTTPException(404, "单词不存在")
    return VocabResponse(**row)


@router.put("/vocab/{vocab_id}", response_model=VocabResponse)
async def update_vocab_endpoint(vocab_id: int, patch: VocabUpdate) -> VocabResponse:
    row = await asyncio.to_thread(
        db.update_vocab, vocab_id, patch.model_dump(exclude_unset=True)
    )
    if row is None:
        raise HTTPException(404, "单词不存在")
    return VocabResponse(**row)


@router.delete("/vocab/{vocab_id}", status_code=204)
async def delete_vocab_endpoint(vocab_id: int) -> None:
    ok = await asyncio.to_thread(db.delete_vocab, vocab_id)
    if not ok:
        raise HTTPException(404, "单词不存在")
