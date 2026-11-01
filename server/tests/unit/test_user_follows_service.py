# -*- coding: utf-8 -*-
"""Following a person, and the feed that following feeds.

`user_follows_service.toggle` borrows the case follow's DELETE-then-maybe-INSERT
trick; `cases_service.list_feed_cases` is "My Feed", which must now take in the
cases filed by people the viewer follows as well as the cases they follow.

No database: the fake keeps a set of follows and answers from it, and the feed
tests assert on the SQL sent rather than on rows a server would return.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services import cases_service, user_follows_service

pytestmark = pytest.mark.unit

ME = 11
THEM = 12


class _FakeDb:
    def __init__(self, status="active", exists=True):
        self.following: set[tuple[int, int]] = set()
        self.status = status
        self.exists = exists
        self.writes: list[tuple[str, tuple]] = []
        self.selects: list[tuple[str, list]] = []

    def query_one(self, sql, params=()):
        if "FROM users WHERE id" in sql:
            return {"id": params[0], "status": self.status} if self.exists else None
        if "FROM user_follows" in sql:
            return {"hit": 1} if (params[0], params[1]) in self.following else None
        return None

    def query_all(self, sql, params=()):
        self.selects.append((sql, list(params)))
        return []

    def query_value(self, sql, params=(), default=None):
        self.selects.append((sql, list(params)))
        if "FROM user_follows" in sql and "f.followee_id = %s" in sql:
            return sum(1 for _, followee in self.following if followee == params[0])
        return 7

    def execute(self, sql, params=()):
        self.writes.append((sql, params))
        key = (params[0], params[1])
        if "DELETE FROM user_follows" in sql:
            if key in self.following:
                self.following.discard(key)
                return SimpleNamespace(rowcount=1)
            return SimpleNamespace(rowcount=0)
        if "INSERT INTO user_follows" in sql:
            self.following.add(key)
        return SimpleNamespace(rowcount=1)

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


# --- the button -------------------------------------------------------------


def test_toggle_round_trips():
    db = _FakeDb()

    assert user_follows_service.toggle(ME, THEM, conn=db) == (
        "ok",
        {"following": True, "follower_count": 1},
    )
    assert (ME, THEM) in db.following

    assert user_follows_service.toggle(ME, THEM, conn=db) == (
        "ok",
        {"following": False, "follower_count": 0},
    )
    assert (ME, THEM) not in db.following


def test_you_cannot_follow_yourself():
    db = _FakeDb()
    assert user_follows_service.toggle(ME, ME, conn=db) == ("invalid", {})
    assert db.writes == []


@pytest.mark.parametrize("kwargs", [{"exists": False}, {"status": "banned"}])
def test_a_missing_or_banned_person_cannot_be_followed(kwargs):
    db = _FakeDb(**kwargs)
    assert user_follows_service.toggle(ME, THEM, conn=db) == ("not_found", {})
    assert db.writes == []


def test_anonymous_viewers_follow_nobody():
    assert user_follows_service.is_following(None, THEM) is False


# --- My Feed ----------------------------------------------------------------


def test_the_feed_takes_in_cases_filed_by_people_the_viewer_follows():
    db = _FakeDb()
    cases_service.list_feed_cases(ME, limit=20, offset=0, conn=db)

    sql, params = db.selects[0]
    assert "FROM case_follows cf WHERE cf.case_id = c.id AND cf.user_id = %s" in sql
    assert "c.author_id IN (SELECT uf.followee_id FROM user_follows uf" in sql
    # The two membership ids, then the visibility one, then the page.
    assert params == [ME, ME, ME, 20, 0]


def test_the_feed_and_its_count_filter_the_same_way():
    """A wider count leaves a "load more" that never loads anything."""
    list_db, count_db = _FakeDb(), _FakeDb()
    cases_service.list_feed_cases(ME, conn=list_db)
    cases_service.count_feed_cases(ME, conn=count_db)

    list_sql, _ = list_db.selects[0]
    count_sql, count_params = count_db.selects[0]
    where = count_sql.split("WHERE", 1)[1]
    assert where in list_sql
    assert count_params == [ME, ME, ME]
