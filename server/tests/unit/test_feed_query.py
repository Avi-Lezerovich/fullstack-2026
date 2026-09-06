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
            "FROM case_follows WHERE user_id": [{"case_id": 1}],
            "FROM case_activity": [{"case_id": 1, "last_activity_at": WHEN}],
        }
    )
    meta = cases_service._counts_for([1, 2], VIEWER, db)

    assert meta[1]["viewer_is_following"] is True
    assert meta[2]["viewer_is_following"] is False
    assert meta[1]["last_activity_at"] == WHEN
    assert meta[2]["last_activity_at"] is None


def test_an_anonymous_viewer_costs_no_follows_query():
    """Same short circuit the likes lookup has: nobody to ask about.

    The follower TOTAL is still counted - that is public, and the card shows it
    signed out. What is skipped is "does this viewer follow it", which has no
    viewer to ask about.
    """
    db = _RecordingDb()
    meta = cases_service._counts_for([1], None, db)

    assert not any("FROM case_follows WHERE user_id" in sql for sql, _ in db.selects)
    assert meta[1]["viewer_is_following"] is False


def test_the_batch_counts_followers_for_a_whole_page_in_one_query():
    """The count that puts "N users tracking this" on a card. One GROUP BY for
    the page, not one query per case."""
    db = _RecordingDb(
        {"COUNT(*) AS n FROM case_follows": [{"case_id": 1, "n": 3}]}
    )
    meta = cases_service._counts_for([1, 2], VIEWER, db)

    assert meta[1]["follow_count"] == 3
    assert meta[2]["follow_count"] == 0

    grouped = [
        sql for sql, _ in db.selects if "COUNT(*) AS n FROM case_follows" in sql
    ]
    assert len(grouped) == 1


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


def test_shape_case_carries_the_follower_total():
    assert cases_service.shape_case(_row(), follow_count=4)["follow_count"] == 4


def test_shape_case_defaults_are_the_signed_out_answer():
    shaped = cases_service.shape_case(_row())

    assert shaped["viewer_is_following"] is False
    assert shaped["last_activity_at"] is None
    assert shaped["follow_count"] == 0


# --- somebody else's list ---------------------------------------------------
#
# The same query serves /cases/feed and the "tracking N cases" list on a
# profile. The difference is entirely in the ids: whose follows are joined, and
# whose hidden filings stay visible.


def test_reading_someone_elses_follows_binds_the_owner_then_the_viewer():
    db = _RecordingDb()
    cases_service.list_followed_cases(VIEWER, viewer_id=VIEWER + 1, limit=20, offset=0, conn=db)

    _, params = _select_naming(db, "JOIN case_follows")
    assert params == [VIEWER, VIEWER + 1, 20, 0]


def test_a_strangers_hidden_filing_stays_hidden_in_someone_elses_list():
    """The visibility carve-out binds the VIEWER, so following a hidden case
    does not put it on a profile a stranger is reading."""
    db = _RecordingDb()
    cases_service.list_followed_cases(VIEWER, viewer_id=VIEWER + 1, limit=20, offset=0, conn=db)

    sql, params = _select_naming(db, "JOIN case_follows")
    assert "(c.moderation_status IN ('published', 'flagged') OR c.author_id = %s)" in sql
    assert params[1] == VIEWER + 1


def test_the_profile_count_and_its_list_agree_on_the_ids_they_bind():
    """The profile shows this count beside that list. Different ids here would
    show "tracking 5" above three rows."""
    list_db = _RecordingDb()
    cases_service.list_followed_cases(VIEWER, viewer_id=VIEWER + 1, limit=20, offset=0, conn=list_db)
    _, list_params = _select_naming(list_db, "JOIN case_follows")

    count_db = _RecordingDb()
    cases_service.count_followed_cases(VIEWER, viewer_id=VIEWER + 1, conn=count_db)
    _, count_params = _select_naming(count_db, "COUNT(*)")

    assert count_params == list_params[:2] == [VIEWER, VIEWER + 1]
