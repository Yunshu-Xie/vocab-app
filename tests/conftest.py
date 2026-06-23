"""Pytest configuration: isolate each test with a temp SQLite file."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """Point settings.db_path at a per-test temp file."""
    from app.config import settings
    from app.services import db as db_module

    db_file = tmp_path / "test_vocab.db"
    monkeypatch.setattr(settings, "db_path", str(db_file))

    db_module.init_db()

    yield db_file
