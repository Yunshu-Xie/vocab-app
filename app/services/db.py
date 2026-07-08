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
CREATE UNIQUE INDEX IF NOT EXISTS idx_usage_unique
    ON vocab_usage(vocab_id, source_sentence);
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


def _fetch_usages_bulk(
    conn: sqlite3.Connection, vocab_ids: list[int]
) -> dict[int, list[dict]]:
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
        entry = _row_to_dict(r)
        by_vocab[entry.pop("vocab_id")].append(entry)
    return by_vocab


def _get_vocab_with_usages(conn: sqlite3.Connection, vocab_id: int) -> Optional[dict]:
    row = conn.execute("SELECT * FROM vocab WHERE id = ?", (vocab_id,)).fetchone()
    if row is None:
        return None
    result = _row_to_dict(row)
    result["usages"] = _fetch_usages_bulk(conn, [vocab_id])[vocab_id]
    return result


def upsert_vocab(data: dict, db_path: Optional[str] = None) -> tuple[dict, bool]:
    """Insert a vocab entry, or record another usage of an existing (word, pos).

    Meeting a known word/phrase again isn't an error worth blocking on — the
    sentence it was met in is appended to its usage history instead (the
    UNIQUE index on (vocab_id, source_sentence) makes re-adding the exact
    same sentence a no-op). Returns (row incl. usages, created).
    """
    created_at = datetime.now(timezone.utc).isoformat()
    with get_conn(db_path) as conn:
        existing = conn.execute(
            "SELECT id FROM vocab WHERE word = ? AND pos = ?",
            (data["word"], data.get("pos", "")),
        ).fetchone()
        if existing is None:
            created = True
            vocab_id = conn.execute(
                """
                INSERT INTO vocab (word, lemma, pos, meaning, example, notes, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data["word"],
                    data.get("lemma", ""),
                    data.get("pos", ""),
                    data["meaning"],
                    data.get("example", ""),
                    data.get("notes", ""),
                    created_at,
                ),
            ).lastrowid
        else:
            created = False
            vocab_id = existing["id"]

        conn.execute(
            "INSERT OR IGNORE INTO vocab_usage "
            "(vocab_id, source_sentence, source_translation, created_at) "
            "VALUES (?, ?, ?, ?)",
            (
                vocab_id,
                data.get("source_sentence", ""),
                data.get("source_translation", ""),
                created_at,
            ),
        )
        return _get_vocab_with_usages(conn, vocab_id), created


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
        return _get_vocab_with_usages(conn, vocab_id)


def update_vocab(
    vocab_id: int, patch: dict, db_path: Optional[str] = None
) -> Optional[dict]:
    fields = {k: v for k, v in patch.items() if v is not None}
    if not fields:
        return get_vocab(vocab_id, db_path)

    set_clause = ", ".join(f"{k} = ?" for k in fields)
    params = [*fields.values(), vocab_id]

    with get_conn(db_path) as conn:
        cursor = conn.execute(f"UPDATE vocab SET {set_clause} WHERE id = ?", params)
        if cursor.rowcount == 0:
            return None
        return _get_vocab_with_usages(conn, vocab_id)


def delete_vocab(vocab_id: int, db_path: Optional[str] = None) -> bool:
    with get_conn(db_path) as conn:
        cursor = conn.execute("DELETE FROM vocab WHERE id = ?", (vocab_id,))
        return cursor.rowcount > 0
