# -*- coding: utf-8 -*-
"""The personal feed's query, and the batch that fills its two new fields.

Two claims worth pinning, both of which fail silently rather than loudly:

  * `count_followed_cases` must filter exactly as `list_followed_cases` does.
    A total counted over a wider set leaves a "load more" button that can never
    load anything - the same trap `count_cases` documents.
  * The ordering is COALESCE(activity, filed_at) DESC. Without the COALESCE any
    case whose activity row has not been written yet - anything filed before
    this shipped and not yet backfilled - sorts last forever.

There is no MySQL in the unit suite, so what these assert is the SQL the service
sends and the parameters bound to it, not the rows a server would return.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from app.services import cases_service

pytestmark = pytest.mark.unit

VIEWER = 9
WHEN = datetime(2026, 3, 1, 12, 30, 45)


class _RecordingDb:
    """Answers nothing useful; remembers every question."""

    def __init__(self, rows_by_fragment=None):
        self.rows_by_fragment = rows_by_fragment or {}
        self.selects: list[tuple[str, list]] = []

    def query_all(self, sql, params=()):
        self.selects.append((sql, list(params)))
        for fragment, rows in self.rows_by_fragment.items():
            if fragment in sql:
                return rows
        return []

    def query_value(self, sql, params=(), default=None):
        self.selects.append((sql, list(params)))
        return 7

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


def _select_naming(db, fragment):
    for sql, params in db.selects:
        if fragment in sql:
            return sql, params
    raise AssertionError(f"no query mentioned {fragment!r}")


# --- the list query ---------------------------------------------------------


def test_the_feed_is_limited_to_what_the_viewer_follows():
    db = _RecordingDb()
    cases_service.list_followed_cases(VIEWER, limit=20, offset=0, conn=db)

    sql, _ = _select_naming(db, "JOIN case_follows")
    assert "JOIN case_follows cf ON cf.case_id = c.id AND cf.user_id = %s" in sql


def test_the_feed_orders_by_activity_falling_back_to_the_filing():
    db = _RecordingDb()
    cases_service.list_followed_cases(VIEWER, limit=20, offset=0, conn=db)

    sql, _ = _select_naming(db, "JOIN case_follows")
    assert "LEFT JOIN case_activity ca ON ca.case_id = c.id" in sql
    assert "ORDER BY COALESCE(ca.last_activity_at, c.filed_at) DESC, c.id DESC" in sql


def test_the_feed_hides_other_peoples_hidden_cases_but_not_your_own():
    """Exactly the carve-out get_case makes, and no admin special case."""
    db = _RecordingDb()
    cases_service.list_followed_cases(VIEWER, limit=20, offset=0, conn=db)

    sql, _ = _select_naming(db, "JOIN case_follows")
    assert "(c.moderation_status IN ('published', 'flagged') OR c.author_id = %s)" in sql


def test_the_feed_binds_the_viewer_twice_then_the_page():
    """The join takes one, the visibility carve-out takes the other."""
    db = _RecordingDb()
    cases_service.list_followed_cases(VIEWER, limit=20, offset=40, conn=db)

    _, params = _select_naming(db, "JOIN case_follows")
    assert params == [VIEWER, VIEWER, 20, 40]


# --- the count query --------------------------------------------------------


def test_count_followed_cases_filters_exactly_as_the_list_does():
    list_db = _RecordingDb()
    cases_service.list_followed_cases(VIEWER, limit=20, offset=0, conn=list_db)
    list_sql, _ = _select_naming(list_db, "JOIN case_follows")

    count_db = _RecordingDb()
    cases_service.count_followed_cases(VIEWER, conn=count_db)
    count_sql, count_params = _select_naming(count_db, "COUNT(*)")

    for clause in (
        "JOIN case_follows cf ON cf.case_id = c.id AND cf.user_id = %s",
        "(c.moderation_status IN ('published', 'flagged') OR c.author_id = %s)",
    ):
        assert clause in list_sql
        assert clause in count_sql

    assert "LIMIT" not in count_sql
    assert count_params == [VIEWER, VIEWER]


# --- the batch that fills the card ------------------------------------------


def test_the_batch_answers_following_and_activity_for_a_whole_page():
    db = _RecordingDb(
        {
            "FROM case_follows": [{"case_id": 1}],
            "FROM case_activity": [{"case_id": 1, "last_activity_at": WHEN}],
        }
    )
    meta = cases_service._counts_for([1, 2], VIEWER, db)

    assert meta[1]["viewer_is_following"] is True
    assert meta[2]["viewer_is_following"] is False
    assert meta[1]["last_activity_at"] == WHEN
    assert meta[2]["last_activity_at"] is None


def test_an_anonymous_viewer_costs_no_follows_query():
    """Same short circuit the likes lookup has: nobody to ask about."""
    db = _RecordingDb()
    meta = cases_service._counts_for([1], None, db)

    assert not any("FROM case_follows" in sql for sql, _ in db.selects)
    assert meta[1]["viewer_is_following"] is False


# --- shaping ----------------------------------------------------------------


def _row():
    return {
        "id": 1, "title": "t", "body": "b", "image_url": None, "author_id": 2,
        "defendant_text": "d", "defendant_user_id": None,
        "status": "witness_phase", "phase_deadline_at": None, "filed_at": None,
        "verdict": None, "sentence_text": None, "verdict_at": None, "closed_at": None,
        "moderation_status": "published", "created_at": None,
        "author_name": "א", "author_avatar": None, "author_is_bot": 0,
        "defendant_name": None, "defendant_avatar": None, "defendant_is_bot": None,
    }


def test_shape_case_exposes_the_two_new_fields():
    shaped = cases_service.shape_case(
        _row(), viewer_is_following=True, last_activity_at=WHEN
    )

    assert shaped["viewer_is_following"] is True
    assert shaped["last_activity_at"] == "2026-03-01T12:30:45"


def test_shape_case_defaults_are_the_signed_out_answer():
    shaped = cases_service.shape_case(_row())

    assert shaped["viewer_is_following"] is False
    assert shaped["last_activity_at"] is None
