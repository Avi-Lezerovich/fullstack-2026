# -*- coding: utf-8 -*-
"""Filing a lawsuit puts it in your own feed, without you asking.

Three people are automatically interested in a case: whoever filed it, whoever
was named as its registered defendant, and (elsewhere, in summons_service)
whoever testified. This pins the first two, and the activity row that makes the
filing sortable at all.

The interesting edge is the rejected filing. It is still INSERTed - the audit
trail is the whole point - but it never publishes, so it must not turn up in
anybody's feed either.

No database: the connection is a fake that records what it was asked.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services import cases_service

pytestmark = pytest.mark.unit

CASE = 21
AUTHOR = 5
DEFENDANT = 8


class _FakeDb:
    def __init__(self):
        self.writes: list[tuple[str, tuple]] = []
        self.commits = 0

    def query_one(self, sql, params=()):
        return None

    def query_all(self, sql, params=()):
        return []

    def query_value(self, sql, params=(), default=None):
        return default

    def execute(self, sql, params=()):
        self.writes.append((sql, params))
        return SimpleNamespace(rowcount=1, lastrowid=CASE)

    def execute_many(self, sql, seq):
        self.writes.append((sql, tuple(seq)))
        return SimpleNamespace(rowcount=len(list(seq)), lastrowid=CASE)

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass

    def close(self):
        pass


def _writes_naming(db, fragment):
    return [(sql, params) for sql, params in db.writes if fragment in sql]


def _file(db, **kwargs):
    """A filing that skips the content scan, so no model is involved."""
    return cases_service.create_case(
        AUTHOR,
        "התביעה נגד המדפסת",
        "היא צפצפה שלוש פעמים ברצף.",
        "המדפסת במשרד",
        moderation_status=kwargs.pop("moderation_status", "published"),
        screen=False,
        conn=db,
        **kwargs,
    )


def test_filing_auto_follows_the_author():
    db = _FakeDb()
    result, case_id = _file(db)

    assert (result, case_id) == ("ok", CASE)
    follows = _writes_naming(db, "INSERT INTO case_follows")
    assert len(follows) == 1
    assert follows[0][1] == (CASE, AUTHOR, "auto")


def test_a_named_defendant_is_auto_followed_too():
    """Being sued is at least as interesting as suing."""
    db = _FakeDb()
    _file(db, defendant_user_id=DEFENDANT)

    followed = [params for _, params in _writes_naming(db, "INSERT INTO case_follows")]
    assert followed == [(CASE, AUTHOR, "auto"), (CASE, DEFENDANT, "auto")]


def test_a_free_text_defendant_follows_nobody_extra():
    """"התביעה נגד יום שני" has no account to add."""
    db = _FakeDb()
    _file(db)

    assert len(_writes_naming(db, "INSERT INTO case_follows")) == 1


def test_filing_records_activity():
    db = _FakeDb()
    _file(db)

    activity = _writes_naming(db, "INSERT INTO case_activity")
    assert len(activity) == 1
    assert activity[0][1] == (CASE, "filed")


def test_a_rejected_filing_gets_no_feed_presence():
    """The row survives for the admin queue; the feed never learns about it."""
    db = _FakeDb()
    result, _ = _file(db, moderation_status="rejected", defendant_user_id=DEFENDANT)

    assert result == "rejected"
    assert _writes_naming(db, "INSERT INTO case_follows") == []
    assert _writes_naming(db, "INSERT INTO case_activity") == []


def test_the_follow_and_the_filing_are_one_transaction():
    """Nothing commits inside create_case when the caller owns the connection."""
    db = _FakeDb()
    _file(db)

    assert db.commits == 0
