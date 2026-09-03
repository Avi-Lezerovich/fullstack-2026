# -*- coding: utf-8 -*-
"""The one timestamp the personal feed sorts on.

`case_activity` holds a single row per case. Everything about it that could go
wrong is about *when* it is written rather than what: a second write must move
the timestamp rather than fail on the primary key, and the write must belong to
the caller's transaction so a case cannot end up advertising activity that was
rolled back.

No database: the connection is a fake that records what it was asked.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services import case_activity_service

pytestmark = pytest.mark.unit

CASE = 4


class _FakeDb:
    """Records every write, and whether anybody committed it."""

    def __init__(self):
        self.writes: list[tuple[str, tuple]] = []
        self.commits = 0

    def execute(self, sql, params=()):
        self.writes.append((sql, params))
        return SimpleNamespace(rowcount=1, lastrowid=1)

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass

    def close(self):
        pass


def test_touch_upserts_rather_than_inserting():
    db = _FakeDb()
    case_activity_service.touch(CASE, "filed", conn=db)

    assert len(db.writes) == 1
    sql, params = db.writes[0]
    assert "INSERT INTO case_activity" in sql
    assert "ON DUPLICATE KEY UPDATE" in sql
    assert params == (CASE, "filed")


def test_touch_moves_the_timestamp_forward():
    """The second write must rewrite last_activity_at, not leave the first one.

    A plain INSERT ... ON DUPLICATE KEY UPDATE that only touched the kind would
    look correct and quietly freeze the feed's ordering at each case's first
    event.
    """
    db = _FakeDb()
    case_activity_service.touch(CASE, "filed", conn=db)
    case_activity_service.touch(CASE, "comment", conn=db)

    second_sql, second_params = db.writes[1]
    assert "last_activity_at = UTC_TIMESTAMP()" in second_sql
    assert "last_activity_kind = VALUES(last_activity_kind)" in second_sql
    assert second_params == (CASE, "comment")


def test_the_clock_is_the_database_and_the_kind_is_bound():
    """One clock, and no kind spliced into the SQL text."""
    db = _FakeDb()
    case_activity_service.touch(CASE, "verdict", conn=db)

    sql, params = db.writes[0]
    assert "UTC_TIMESTAMP()" in sql
    assert "verdict" not in sql
    assert params[1] == "verdict"


def test_touch_leaves_a_borrowed_transaction_alone():
    """The caller owns the commit; the bump only joins it."""
    db = _FakeDb()
    case_activity_service.touch(CASE, "closed", conn=db)

    assert db.commits == 0


def test_touch_commits_when_it_opened_the_connection_itself(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr("app.db.connect", lambda: db)

    case_activity_service.touch(CASE, "closed")

    assert db.commits == 1
