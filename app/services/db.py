from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator, Optional

from app.config import settings

_DDL = """
CREATE TABLE IF NOT EXISTS vocab (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    word TEXT NOT NULL,
    lemma TEXT NOT NULL DEFAULT '',
    pos TEXT NOT NULL DEFAULT '',
    meaning TEXT NOT NULL,
    example TEXT NOT NULL DEFAULT '',
    source_sentence TEXT NOT NULL DEFAULT '',
    source_translation TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    UNIQUE(word, pos)
);
CREATE INDEX IF NOT EXISTS idx_vocab_created ON vocab(created_at DESC);
"""


def init_db(db_path: Optional[str] = None) -> None:
    path = db_path or settings.db_path
    with sqlite3.connect(path) as conn:
        conn.executescript(_DDL)
        conn.commit()


@contextmanager
def get_conn(db_path: Optional[str] = None) -> Iterator[sqlite3.Connection]:
    path = db_path or settings.db_path
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _row_to_dict(row: sqlite3.Row) -> dict:
    return {k: row[k] for k in row.keys()}


class DuplicateVocabError(Exception):
    """Raised when (word, pos) already exists. Carries the existing row's id."""

    def __init__(self, existing_id: int):
        super().__init__(f"vocab already exists (id={existing_id})")
        self.existing_id = existing_id


def insert_vocab(data: dict, db_path: Optional[str] = None) -> dict:
    """Insert a vocab row. Raises DuplicateVocabError if (word, pos) collides."""
    created_at = datetime.now(timezone.utc).isoformat()
    with get_conn(db_path) as conn:
        existing = conn.execute(
            "SELECT id FROM vocab WHERE word = ? AND pos = ?",
            (data["word"], data.get("pos", "")),
        ).fetchone()
        if existing is not None:
            raise DuplicateVocabError(existing["id"])

        cursor = conn.execute(
            """
            INSERT INTO vocab
              (word, lemma, pos, meaning, example,
               source_sentence, source_translation, notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data["word"],
                data.get("lemma", ""),
                data.get("pos", ""),
                data["meaning"],
                data.get("example", ""),
                data.get("source_sentence", ""),
                data.get("source_translation", ""),
                data.get("notes", ""),
                created_at,
            ),
        )
        new_id = cursor.lastrowid
        row = conn.execute("SELECT * FROM vocab WHERE id = ?", (new_id,)).fetchone()
        return _row_to_dict(row)


def list_vocab(
    q: str = "",
    page: int = 1,
    limit: int = 50,
    db_path: Optional[str] = None,
) -> tuple[list[dict], int]:
    page = max(1, page)
    limit = max(1, min(200, limit))
    offset = (page - 1) * limit

    where = ""
    params: list = []
    if q:
        where = "WHERE word LIKE ? OR lemma LIKE ? OR meaning LIKE ?"
        like = f"%{q}%"
        params = [like, like, like]

    with get_conn(db_path) as conn:
        total = conn.execute(
            f"SELECT COUNT(*) AS c FROM vocab {where}", params
        ).fetchone()["c"]
        rows = conn.execute(
            f"SELECT * FROM vocab {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            [*params, limit, offset],
        ).fetchall()
        return [_row_to_dict(r) for r in rows], total


def get_vocab(vocab_id: int, db_path: Optional[str] = None) -> Optional[dict]:
    with get_conn(db_path) as conn:
        row = conn.execute("SELECT * FROM vocab WHERE id = ?", (vocab_id,)).fetchone()
        return _row_to_dict(row) if row else None


def update_vocab(
    vocab_id: int, patch: dict, db_path: Optional[str] = None
) -> Optional[dict]:
    fields = {k: v for k, v in patch.items() if v is not None}
    if not fields:
        return get_vocab(vocab_id, db_path)

    set_clause = ", ".join(f"{k} = ?" for k in fields)
    params = [*fields.values(), vocab_id]

    with get_conn(db_path) as conn:
        cursor = conn.execute(
            f"UPDATE vocab SET {set_clause} WHERE id = ?", params
        )
        if cursor.rowcount == 0:
            return None
        row = conn.execute(
            "SELECT * FROM vocab WHERE id = ?", (vocab_id,)
        ).fetchone()
        return _row_to_dict(row) if row else None


def delete_vocab(vocab_id: int, db_path: Optional[str] = None) -> bool:
    with get_conn(db_path) as conn:
        cursor = conn.execute("DELETE FROM vocab WHERE id = ?", (vocab_id,))
        return cursor.rowcount > 0
