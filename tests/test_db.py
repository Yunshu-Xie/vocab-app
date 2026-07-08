"""Unit tests for the SQLite vocab service."""

from __future__ import annotations

from app.services import db


def _payload(**overrides) -> dict:
    base = {
        "word": "ubiquitous",
        "lemma": "ubiquitous",
        "pos": "adjective",
        "meaning": "无处不在的",
        "example": "Smartphones are now ubiquitous.",
        "source_sentence": "The ubiquitous smartphone...",
        "source_translation": "无处不在的手机……",
        "notes": "",
    }
    base.update(overrides)
    return base


def test_insert_and_get():
    row, created = db.upsert_vocab(_payload())
    assert created is True
    assert row["id"] > 0
    assert row["word"] == "ubiquitous"
    assert row["created_at"]

    fetched = db.get_vocab(row["id"])
    assert fetched is not None
    assert fetched["word"] == "ubiquitous"


def test_insert_seeds_first_usage():
    row, _ = db.upsert_vocab(_payload(source_sentence="The ubiquitous smartphone..."))
    assert len(row["usages"]) == 1
    assert row["usages"][0]["source_sentence"] == "The ubiquitous smartphone..."


def test_duplicate_word_pos_merges_as_new_usage():
    first, created1 = db.upsert_vocab(_payload())
    merged, created2 = db.upsert_vocab(
        _payload(source_sentence="Plastic is ubiquitous in the ocean.")
    )
    assert created1 is True
    assert created2 is False
    assert merged["id"] == first["id"]
    assert len(merged["usages"]) == 2
    assert merged["usages"][1]["source_sentence"] == "Plastic is ubiquitous in the ocean."


def test_duplicate_same_sentence_does_not_duplicate_usage():
    db.upsert_vocab(_payload())
    merged, created = db.upsert_vocab(_payload())
    assert created is False
    assert len(merged["usages"]) == 1


def test_same_word_different_pos_creates_new_entry():
    db.upsert_vocab(_payload(pos="adjective"))
    row2, created = db.upsert_vocab(_payload(pos="noun"))
    assert created is True
    assert row2["pos"] == "noun"


def test_list_and_search():
    db.upsert_vocab(_payload(word="ubiquitous", lemma="ubiquitous", pos="adjective"))
    db.upsert_vocab(
        _payload(word="ephemeral", lemma="ephemeral", pos="adjective", meaning="短暂的")
    )
    db.upsert_vocab(
        _payload(word="serendipity", lemma="serendipity", pos="noun", meaning="意外发现")
    )

    items, total = db.list_vocab()
    assert total == 3
    assert len(items) == 3

    items, total = db.list_vocab(q="ubiq")
    assert total == 1
    assert items[0]["word"] == "ubiquitous"

    items, total = db.list_vocab(q="意外")
    assert total == 1
    assert items[0]["word"] == "serendipity"


def test_update():
    row, _ = db.upsert_vocab(_payload())
    updated = db.update_vocab(row["id"], {"notes": "记一下"})
    assert updated is not None
    assert updated["notes"] == "记一下"
    # Unchanged fields remain
    assert updated["word"] == "ubiquitous"


def test_update_missing_returns_none():
    assert db.update_vocab(9999, {"notes": "x"}) is None


def test_delete():
    row, _ = db.upsert_vocab(_payload())
    assert db.delete_vocab(row["id"]) is True
    assert db.get_vocab(row["id"]) is None
    assert db.delete_vocab(row["id"]) is False


def test_delete_cascades_usages():
    row, _ = db.upsert_vocab(_payload())
    db.upsert_vocab(_payload(source_sentence="Another sentence, ubiquitous again."))
    assert db.delete_vocab(row["id"]) is True

    with db.get_conn() as conn:
        remaining = conn.execute(
            "SELECT COUNT(*) AS c FROM vocab_usage WHERE vocab_id = ?", (row["id"],)
        ).fetchone()["c"]
    assert remaining == 0


def test_pagination():
    for i in range(25):
        db.upsert_vocab(_payload(word=f"word{i:02d}", pos="noun"))
    items, total = db.list_vocab(page=1, limit=10)
    assert total == 25
    assert len(items) == 10
    items2, _ = db.list_vocab(page=2, limit=10)
    assert len(items2) == 10
    # Page 1 and page 2 are disjoint
    ids1 = {i["id"] for i in items}
    ids2 = {i["id"] for i in items2}
    assert not (ids1 & ids2)
