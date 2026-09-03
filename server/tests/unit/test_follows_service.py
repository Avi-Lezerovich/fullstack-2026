# -*- coding: utf-8 -*-
"""Following a lawsuit, and the two doors into `case_follows`.

`toggle_follow` is the button, and borrows `likes_service.toggle_like`'s trick:
DELETE first and read the rowcount, because that answers "were they following?"
without a separate SELECT that another request could invalidate between the two.

`follow` is the automatic path - you filed it, you were named its defendant, you
testified in it - and has to be safe on a retried worker tick.

No database: the fake keeps a set of follows and answers from it.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services import follows_service

pytestmark = pytest.mark.unit

CASE = 3
USER = 11


class _FakeDb:
    """A tiny stand-in for `case_follows`, plus a record of every write."""

    def __init__(self, moderation_status="published", case_exists=True):
        self.following: set[tuple[int, int]] = set()
        self.moderation_status = moderation_status
        self.case_exists = case_exists
        self.rows: list[dict] = []
        self.writes: list[tuple[str, tuple]] = []
        self.commits = 0

    def query_one(self, sql, params=()):
        if "FROM cases WHERE id" in sql:
            if not self.case_exists:
                return None
            return {"id": CASE, "moderation_status": self.moderation_status}
        if "FROM case_follows" in sql:
            return {"hit": 1} if (params[0], params[1]) in self.following else None
        return None

    def query_all(self, sql, params=()):
        return self.rows

    def execute(self, sql, params=()):
        self.writes.append((sql, params))
        if "DELETE FROM case_follows" in sql:
            key = (params[0], params[1])
            if key in self.following:
                self.following.discard(key)
                return SimpleNamespace(rowcount=1, lastrowid=0)
            return SimpleNamespace(rowcount=0, lastrowid=0)
        if "INSERT INTO case_follows" in sql:
            self.following.add((params[0], params[1]))
        return SimpleNamespace(rowcount=1, lastrowid=1)

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass

    def close(self):
        pass


def _writes_naming(db, fragment):
    return [(sql, params) for sql, params in db.writes if fragment in sql]


def test_toggle_follow_round_trips():
    """Follow, then unfollow, and the second call must not leave a row behind."""
    db = _FakeDb()

    result, payload = follows_service.toggle_follow(CASE, USER, conn=db)
    assert (result, payload) == ("ok", {"following": True})
    assert (CASE, USER) in db.following

    result, payload = follows_service.toggle_follow(CASE, USER, conn=db)
    assert (result, payload) == ("ok", {"following": False})
    assert (CASE, USER) not in db.following


def test_a_manual_follow_is_marked_manual():
    db = _FakeDb()
    follows_service.toggle_follow(CASE, USER, conn=db)

    sql, params = _writes_naming(db, "INSERT INTO case_follows")[0]
    assert "'manual'" in sql
    assert params == (CASE, USER)


def test_the_delete_rowcount_is_the_previous_state():
    """Unfollowing writes a DELETE and nothing else."""
    db = _FakeDb()
    db.following.add((CASE, USER))

    follows_service.toggle_follow(CASE, USER, conn=db)

    assert len(_writes_naming(db, "DELETE FROM case_follows")) == 1
    assert _writes_naming(db, "INSERT INTO case_follows") == []


def test_a_missing_case_cannot_be_followed():
    db = _FakeDb(case_exists=False)

    assert follows_service.toggle_follow(CASE, USER, conn=db) == ("not_found", {})
    assert db.writes == []


@pytest.mark.parametrize("status", ["hidden", "rejected"])
def test_an_invisible_case_cannot_be_followed(status):
    """The same answer a hidden case gives every other social endpoint."""
    db = _FakeDb(moderation_status=status)

    assert follows_service.toggle_follow(CASE, USER, conn=db) == ("not_found", {})
    assert db.writes == []


def test_follow_is_idempotent():
    """The automatic paths run again on a retried tick; the second run is a no-op."""
    db = _FakeDb()
    follows_service.follow(CASE, USER, source="auto", conn=db)

    sql, params = _writes_naming(db, "INSERT INTO case_follows")[0]
    assert "ON DUPLICATE KEY UPDATE case_id = case_id" in sql
    assert params == (CASE, USER, "auto")


def test_following_never_notifies_anybody():
    """A follow is a private bookmark. A like is not, and does notify."""
    db = _FakeDb()
    follows_service.toggle_follow(CASE, USER, conn=db)
    follows_service.follow(CASE, USER + 1, source="auto", conn=db)

    assert _writes_naming(db, "notifications") == []


def test_toggle_follow_leaves_a_borrowed_transaction_alone():
    db = _FakeDb()
    follows_service.toggle_follow(CASE, USER, conn=db)

    assert db.commits == 0


def test_is_following():
    db = _FakeDb()
    db.following.add((CASE, USER))

    assert follows_service.is_following(CASE, USER, conn=db) is True
    assert follows_service.is_following(CASE, USER + 1, conn=db) is False


def test_an_anonymous_viewer_follows_nothing_without_asking():
    """No user id, no query - the same short circuit likes_service.has_liked has."""
    db = _FakeDb()

    assert follows_service.is_following(CASE, None, conn=db) is False


def test_followed_case_ids():
    db = _FakeDb()
    db.rows = [{"case_id": 1}, {"case_id": 2}]

    assert follows_service.followed_case_ids(USER, conn=db) == {1, 2}
