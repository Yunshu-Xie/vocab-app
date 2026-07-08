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

CREATE TABLE IF NOT EXISTS vocab_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vocab_id INTEGER NOT NULL REFERENCES vocab(id) ON DELETE CASCADE,
    source_sentence TEXT NOT NULL DEFAULT '',
    source_translation TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_usage_vocab ON vocab_usage(vocab_id);
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
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _row_to_dict(row: sqlite3.Row) -> dict:
    return {k: row[k] for k in row.keys()}


def _fetch_usages(conn: sqlite3.Connection, vocab_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT source_sentence, source_translation, created_at "
        "FROM vocab_usage WHERE vocab_id = ? ORDER BY created_at ASC",
        (vocab_id,),
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def _fetch_usages_bulk(conn: sqlite3.Connection, vocab_ids: list[int]) -> dict[int, list[dict]]:
    if not vocab_ids:
        return {}
    placeholders = ",".join("?" for _ in vocab_ids)
    rows = conn.execute(
        f"SELECT vocab_id, source_sentence, source_translation, created_at "
        f"FROM vocab_usage WHERE vocab_id IN ({placeholders}) ORDER BY created_at ASC",
        vocab_ids,
    ).fetchall()
    by_vocab: dict[int, list[dict]] = {vid: [] for vid in vocab_ids}
    for r in rows:
        by_vocab[r["vocab_id"]].append(
            {
                "source_sentence": r["source_sentence"],
                "source_translation": r["source_translation"],
                "created_at": r["created_at"],
            }
        )
    return by_vocab


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
        # The usage that created this entry is usage #1, so `usages` is a
        # complete history from the start rather than a special-cased list
        # that only holds usage #2 onward.
        conn.execute(
            "INSERT INTO vocab_usage (vocab_id, source_sentence, source_translation, created_at) "
            "VALUES (?, ?, ?, ?)",
            (
                new_id,
                data.get("source_sentence", ""),
                data.get("source_translation", ""),
                created_at,
            ),
        )
        row = conn.execute("SELECT * FROM vocab WHERE id = ?", (new_id,)).fetchone()
        result = _row_to_dict(row)
        result["usages"] = _fetch_usages(conn, new_id)
        return result


def add_vocab_usage(
    vocab_id: int,
    source_sentence: str,
    source_translation: str = "",
    db_path: Optional[str] = None,
) -> Optional[dict]:
    """Record another sentence a known word/phrase was encountered in.

    Used when a duplicate (word, pos) is added instead of rejecting it
    outright, so re-meeting a word in a new sentence grows its usage
    history rather than being silently dropped. A no-op if this exact
    sentence is already recorded (guards against duplicate-click retries).
    """
    with get_conn(db_path) as conn:
        row = conn.execute("SELECT id FROM vocab WHERE id = ?", (vocab_id,)).fetchone()
        if row is None:
            return None

        dup = conn.execute(
            "SELECT id FROM vocab_usage WHERE vocab_id = ? AND source_sentence = ?",
            (vocab_id, source_sentence),
        ).fetchone()
        if dup is None:
            conn.execute(
                "INSERT INTO vocab_usage "
                "(vocab_id, source_sentence, source_translation, created_at) "
                "VALUES (?, ?, ?, ?)",
                (
                    vocab_id,
                    source_sentence,
                    source_translation,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

        vocab_row = conn.execute("SELECT * FROM vocab WHERE id = ?", (vocab_id,)).fetchone()
        result = _row_to_dict(vocab_row)
        result["usages"] = _fetch_usages(conn, vocab_id)
        return result


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
        total = conn.execute(f"SELECT COUNT(*) AS c FROM vocab {where}", params).fetchone()["c"]
        rows = conn.execute(
            f"SELECT * FROM vocab {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            [*params, limit, offset],
        ).fetchall()
        items = [_row_to_dict(r) for r in rows]
        usages_by_id = _fetch_usages_bulk(conn, [i["id"] for i in items])
        for item in items:
            item["usages"] = usages_by_id.get(item["id"], [])
        return items, total


def get_vocab(vocab_id: int, db_path: Optional[str] = None) -> Optional[dict]:
    with get_conn(db_path) as conn:
        row = conn.execute("SELECT * FROM vocab WHERE id = ?", (vocab_id,)).fetchone()
        if row is None:
            return None
        result = _row_to_dict(row)
        result["usages"] = _fetch_usages(conn, vocab_id)
        return result


def update_vocab(vocab_id: int, patch: dict, db_path: Optional[str] = None) -> Optional[dict]:
    fields = {k: v for k, v in patch.items() if v is not None}
    if not fields:
        return get_vocab(vocab_id, db_path)

    set_clause = ", ".join(f"{k} = ?" for k in fields)
    params = [*fields.values(), vocab_id]

    with get_conn(db_path) as conn:
        cursor = conn.execute(f"UPDATE vocab SET {set_clause} WHERE id = ?", params)
        if cursor.rowcount == 0:
            return None
        row = conn.execute("SELECT * FROM vocab WHERE id = ?", (vocab_id,)).fetchone()
        if row is None:
            return None
        result = _row_to_dict(row)
        result["usages"] = _fetch_usages(conn, vocab_id)
        return result


def delete_vocab(vocab_id: int, db_path: Optional[str] = None) -> bool:
    with get_conn(db_path) as conn:
        cursor = conn.execute("DELETE FROM vocab WHERE id = ?", (vocab_id,))
        return cursor.rowcount > 0
