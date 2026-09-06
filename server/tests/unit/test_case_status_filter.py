# -*- coding: utf-8 -*-
"""The courtroom feed's status filter, which one tab needs to name two statuses.

A case that has been decided lives in `verdict_reached` only until the worker
retires it, and in `closed` from then on. "הוכרעו" means both to a reader, so
the filter has to mean both too - and, as ever with these two queries, the
count must mean exactly what the list means or "load more" is left offering a
page that does not exist.

There is no MySQL in the unit suite, so what these assert is the SQL the
service sends and the parameters bound to it, not the rows a server returns.
"""

from __future__ import annotations

import pytest

from app.services import cases_service

pytestmark = pytest.mark.unit

DECIDED = ["verdict_reached", "closed"]


class _RecordingDb:
    """Answers nothing useful; remembers every question."""

    def __init__(self):
        self.selects: list[tuple[str, list]] = []

    def query_all(self, sql, params=()):
        self.selects.append((sql, list(params)))
        return []

    def query_value(self, sql, params=(), default=None):
        self.selects.append((sql, list(params)))
        return 0

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


def _only_select(db):
    assert len(db.selects) == 1, "expected exactly one query"
    return db.selects[0]


# --- one status -------------------------------------------------------------


def test_a_single_status_is_still_an_equality_test():
    """The three single-phase tabs must not pay for the decided tab's IN()."""
    db = _RecordingDb()
    cases_service.list_cases(status=["witness_phase"], conn=db)

    sql, params = _only_select(db)
    assert "c.status = %s" in sql
    assert params == ["witness_phase", 20, 0]


def test_a_bare_string_still_works():
    """The service took a plain string before this and callers may still pass
    one; a sequence is the addition, not the replacement."""
    db = _RecordingDb()
    cases_service.list_cases(status="closed", conn=db)

    sql, params = _only_select(db)
    assert "c.status = %s" in sql
    assert params == ["closed", 20, 0]


# --- several statuses -------------------------------------------------------


def test_the_decided_tab_asks_for_both_decided_statuses():
    db = _RecordingDb()
    cases_service.list_cases(status=DECIDED, conn=db)

    sql, params = _only_select(db)
    assert "c.status IN (%s, %s)" in sql
    assert params == ["verdict_reached", "closed", 20, 0]


def test_the_decided_statuses_are_the_ones_a_verdict_leaves_behind():
    """`verdict_reached` is where close_case looks; `closed` is where it puts
    the case. Anything else in this tuple would widen the tab silently."""
    assert cases_service.DECIDED_STATUSES == ("verdict_reached", "closed")
    for status in cases_service.DECIDED_STATUSES:
        assert status in cases_service.CASE_STATUSES


def test_no_status_filters_on_nothing_but_visibility():
    for empty in (None, "", []):
        db = _RecordingDb()
        cases_service.list_cases(status=empty, conn=db)

        sql, params = _only_select(db)
        # `c.status` itself is in the SELECT list either way; what must be
        # absent is a clause testing it.
        assert "c.status = %s" not in sql
        assert "c.status IN" not in sql
        assert params == [20, 0]


# --- the count must agree ---------------------------------------------------


def test_count_cases_filters_on_the_same_statuses_as_the_list():
    """Counting over a wider set than the list shows leaves a "load more"
    button that can never load anything - see count_cases' docstring."""
    list_db = _RecordingDb()
    cases_service.list_cases(status=DECIDED, conn=list_db)
    list_sql, list_params = _only_select(list_db)

    count_db = _RecordingDb()
    cases_service.count_cases(status=DECIDED, conn=count_db)
    count_sql, count_params = _only_select(count_db)

    assert "c.status IN (%s, %s)" in list_sql
    assert "c.status IN (%s, %s)" in count_sql
    # The list's trailing two are LIMIT and OFFSET, which a count has no use for.
    assert count_params == list_params[:-2] == DECIDED
    assert "LIMIT" not in count_sql


def test_the_author_filter_still_binds_before_the_statuses():
    """A profile's list is author + status. The clauses are appended in that
    order, so the parameters must arrive in it."""
    db = _RecordingDb()
    cases_service.list_cases(author_id=4, status=DECIDED, conn=db)

    sql, params = _only_select(db)
    assert "c.author_id = %s" in sql
    assert params == [4, "verdict_reached", "closed", 20, 0]
