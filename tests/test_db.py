"""Unit tests for the SQLite vocab service."""

from __future__ import annotations

import pytest

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
    row = db.insert_vocab(_payload())
    assert row["id"] > 0
    assert row["word"] == "ubiquitous"
    assert row["created_at"]

    fetched = db.get_vocab(row["id"])
    assert fetched is not None
    assert fetched["word"] == "ubiquitous"


def test_duplicate_word_pos_raises():
    db.insert_vocab(_payload())
    with pytest.raises(db.DuplicateVocabError) as exc:
        db.insert_vocab(_payload())
    assert exc.value.existing_id > 0


def test_insert_seeds_first_usage():
    row = db.insert_vocab(_payload(source_sentence="The ubiquitous smartphone..."))
    assert len(row["usages"]) == 1
    assert row["usages"][0]["source_sentence"] == "The ubiquitous smartphone..."


def test_add_vocab_usage_appends_new_sentence():
    row = db.insert_vocab(_payload())
    updated = db.add_vocab_usage(
        row["id"], "Plastic is ubiquitous in the ocean.", "塑料在海洋中无处不在"
    )
    assert updated["id"] == row["id"]
    assert len(updated["usages"]) == 2
    assert updated["usages"][1]["source_sentence"] == "Plastic is ubiquitous in the ocean."


def test_add_vocab_usage_dedupes_identical_sentence():
    row = db.insert_vocab(_payload())
    updated = db.add_vocab_usage(row["id"], row["source_sentence"], row["source_translation"])
    assert len(updated["usages"]) == 1


def test_add_vocab_usage_missing_vocab_returns_none():
    assert db.add_vocab_usage(9999, "Some sentence.") is None


def test_same_word_different_pos_ok():
    db.insert_vocab(_payload(pos="adjective"))
    # Inserting again with a different pos should succeed
    row2 = db.insert_vocab(_payload(pos="noun"))
    assert row2["pos"] == "noun"


def test_list_and_search():
    db.insert_vocab(_payload(word="ubiquitous", lemma="ubiquitous", pos="adjective"))
    db.insert_vocab(
        _payload(word="ephemeral", lemma="ephemeral", pos="adjective", meaning="短暂的")
    )
    db.insert_vocab(
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
    row = db.insert_vocab(_payload())
    updated = db.update_vocab(row["id"], {"notes": "记一下"})
    assert updated is not None
    assert updated["notes"] == "记一下"
    # Unchanged fields remain
    assert updated["word"] == "ubiquitous"


def test_update_missing_returns_none():
    assert db.update_vocab(9999, {"notes": "x"}) is None


def test_delete():
    row = db.insert_vocab(_payload())
    assert db.delete_vocab(row["id"]) is True
    assert db.get_vocab(row["id"]) is None
    assert db.delete_vocab(row["id"]) is False


def test_pagination():
    for i in range(25):
        db.insert_vocab(_payload(word=f"word{i:02d}", pos="noun"))
    items, total = db.list_vocab(page=1, limit=10)
    assert total == 25
    assert len(items) == 10
    items2, _ = db.list_vocab(page=2, limit=10)
    assert len(items2) == 10
    # Page 1 and page 2 are disjoint
    ids1 = {i["id"] for i in items}
    ids2 = {i["id"] for i in items2}
    assert not (ids1 & ids2)
