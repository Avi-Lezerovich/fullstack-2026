# -*- coding: utf-8 -*-
"""The rules MySQL would not let be constraints, so Python has to hold them.

`database/init.sql` names this file twice, and it did not exist:

    "You cannot sue yourself" would naturally be a CHECK here, but MySQL 8
    rejects any CHECK over a column that a foreign key's referential action
    also writes (error 3823). The referential action is worth more than the
    CHECK, so the rule lives in cases_service.create_case() instead and is
    covered by tests/unit/test_cases_rules.py.

The same paragraph appears above `conversations`, for the `user_a_id <
user_b_id` ordering. Both are rules the schema would normally enforce and
cannot, which makes them the two places where a Python-side check is the only
thing standing between the data and a state the database would otherwise have
refused - and therefore exactly the two worth a test of their own.

No database: these are decisions taken before any SQL is sent, and the fake
below records what would have been sent so the test can assert nothing was.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services import cases_service, messages_service

pytestmark = pytest.mark.unit

AUTHOR = 7
SOMEBODY_ELSE = 9


class _RecordingDb:
    """Answers nothing useful; remembers every question."""

    def __init__(self):
        self.writes: list[tuple[str, tuple]] = []

    def query_one(self, sql, params=()):
        return None

    def query_all(self, sql, params=()):
        return []

    def query_value(self, sql, params=(), default=None):
        return default

    def execute(self, sql, params=()):
        self.writes.append((sql, tuple(params)))
        return SimpleNamespace(rowcount=1, lastrowid=1)

    def execute_many(self, sql, seq):
        return SimpleNamespace(rowcount=0, lastrowid=0)

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


# --- you cannot sue yourself ------------------------------------------------


def test_naming_yourself_as_the_defendant_is_refused_before_any_insert():
    """The CHECK constraint MySQL 8 would not accept, as a Python guard.

    Refused rather than silently detached, and refused *first*: a filing that
    inserted and then failed would leave a lawsuit in the database with nobody
    able to explain how it got there.
    """
    db = _RecordingDb()

    result = cases_service.create_case(
        AUTHOR, "תביעה נגד עצמי", "גוף התביעה כאן", "אני", defendant_user_id=AUTHOR, conn=db
    )

    assert result == ("invalid", None)
    assert db.writes == []


def test_the_comparison_survives_an_id_arriving_as_a_string():
    """`int(...)` on both sides, because the id comes off a JSON body.

    A client sending `"7"` where the session holds `7` would slip past a bare
    `==` and file a lawsuit against its own author.
    """
    db = _RecordingDb()

    result = cases_service.create_case(
        AUTHOR, "תביעה נגד עצמי", "גוף התביעה כאן", "אני", defendant_user_id=str(AUTHOR), conn=db
    )

    assert result == ("invalid", None)
    assert db.writes == []


def test_suing_somebody_else_is_of_course_allowed():
    """The rule has to permit the normal case, or it is not a rule.

    Written out because a guard that refused everything would satisfy both
    tests above.
    """
    db = _RecordingDb()

    result, _case_id = cases_service.create_case(
        AUTHOR,
        "תביעה נגד השכן",
        "הוא לקח את החניה שלי ואמר שזה בסדר.",
        "השכן",
        defendant_user_id=SOMEBODY_ELSE,
        screen=False,
        conn=db,
    )

    assert result == "ok"
    assert any("INSERT INTO cases" in sql for sql, _ in db.writes)


def test_a_free_text_defendant_is_never_compared_to_anybody():
    """Most filings name nobody - "התביעה נגד יום שני" has no user id at all.

    The `is not None` guard is what keeps that path away from the comparison
    entirely, rather than relying on `None != AUTHOR` happening to be true.
    """
    db = _RecordingDb()

    result, _case_id = cases_service.create_case(
        AUTHOR, "התביעה נגד יום שני", "יום שני התחיל בלי רשות.", "יום שני", screen=False, conn=db
    )

    assert result == "ok"


@pytest.mark.parametrize(
    ("title", "body", "defendant"),
    [
        ("", "גוף תקין כאן", "הנתבע"),
        ("   ", "גוף תקין כאן", "הנתבע"),
        ("כותרת", "", "הנתבע"),
        ("כותרת", "גוף תקין כאן", "   "),
    ],
    ids=["no-title", "blank-title", "no-body", "blank-defendant"],
)
def test_a_filing_missing_any_of_its_three_required_parts_is_refused(title, body, defendant):
    """Checked before the moderation scan, so an empty filing never costs one."""
    db = _RecordingDb()

    assert cases_service.create_case(AUTHOR, title, body, defendant, conn=db) == ("invalid", None)
    assert db.writes == []


# --- one conversation per pair ----------------------------------------------


def test_the_conversation_pair_is_ordered_whichever_way_round_it_arrives():
    """The `user_a_id < user_b_id` CHECK that MySQL 8 also refused.

    Without it the UNIQUE index would hold both (a, b) and (b, a), and each
    person would see only the half of the correspondence they began.
    """
    assert messages_service._ordered(3, 9) == (3, 9)
    assert messages_service._ordered(9, 3) == (3, 9)


def test_a_conversation_with_yourself_is_refused_by_every_door():
    """`(me, me)` is a perfectly good ordered pair as far as the index is
    concerned, so this rule has nowhere else to live either."""
    db = _RecordingDb()

    assert messages_service.find_conversation(AUTHOR, AUTHOR, conn=db) is None
    assert messages_service.conversation_for_pair(AUTHOR, AUTHOR, conn=db) is None
    assert messages_service.send_message(AUTHOR, AUTHOR, "שלום לי", conn=db) == ("invalid", None)
    assert db.writes == []
