# -*- coding: utf-8 -*-
"""Which events reach a follower's feed, and which deliberately do not.

The rule the feature rests on is that "activity" means the case moved on, not
that somebody reacted to it. So a comment, a testimony, a juror's line, a phase
change, a verdict and a close all bump it - and a like does not, which is why
there is nothing here about `toggle_like`.

The second rule is placement: every bump sits after the guard that decides
whether the work actually landed, and before the commit. A transition that lost
the race returns `already_done` without ever reaching its touch, so a case never
advertises activity that was rolled back.

No database: the connection is a fake that records what it was asked.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services import comments_service, trial_service

pytestmark = pytest.mark.unit

CASE = 3
AUTHOR = 5
SPEAKER = 12


class _FakeDb:
    def __init__(self, rowcount=1):
        self.rowcount = rowcount
        self.writes: list[tuple[str, tuple]] = []
        self.commits = 0

    def query_one(self, sql, params=()):
        if "FROM cases WHERE id" in sql:
            return {
                "id": CASE,
                "title": "התביעה נגד המדפסת",
                "body": "היא צפצפה שלוש פעמים.",
                "defendant_text": "המדפסת במשרד",
                "author_id": AUTHOR,
                "defendant_user_id": None,
                "status": "jury_deliberation",
                "filed_at": None,
            }
        return None

    def query_all(self, sql, params=()):
        return []

    def query_value(self, sql, params=(), default=None):
        return default

    def execute(self, sql, params=()):
        self.writes.append((sql, params))
        return SimpleNamespace(rowcount=self.rowcount, lastrowid=99)

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass

    def close(self):
        pass


def _bumps(db):
    """Every (case_id, kind) this transaction wrote to case_activity."""
    return [
        params for sql, params in db.writes if "INSERT INTO case_activity" in sql
    ]


# --- comments ---------------------------------------------------------------


def _comment(db, **kwargs):
    kwargs.setdefault("moderation_status", "published")
    kwargs.setdefault("screen", False)
    return comments_service.create_comment(
        CASE, SPEAKER, "לא הייתי שם בכלל", conn=db, **kwargs
    )


def test_a_published_comment_bumps_the_case():
    db = _FakeDb()
    _comment(db, role="user")

    assert _bumps(db) == [(CASE, "comment")]


def test_testimony_bumps_the_case_and_says_so():
    """summons_service.testify goes through this door, so it needs no touch."""
    db = _FakeDb()
    _comment(db, role="witness_testimony")

    assert _bumps(db) == [(CASE, "testimony")]


@pytest.mark.parametrize("status", ["hidden", "rejected"])
def test_a_comment_nobody_can_read_bumps_nothing(status):
    db = _FakeDb()
    _comment(db, role="user", moderation_status=status)

    assert _bumps(db) == []


@pytest.mark.parametrize("role", ["jury_deliberation", "verdict"])
def test_court_speech_is_not_bumped_here(role):
    """trial_service bumps those itself, once it knows the transition landed.
    Doing it here as well would double-count and mislabel the kind."""
    db = _FakeDb()
    _comment(db, role=role)

    assert _bumps(db) == []


# --- the trial engine -------------------------------------------------------


def test_closing_a_case_bumps_it():
    db = _FakeDb(rowcount=1)

    assert trial_service.close_case(CASE, conn=db) == "ok"
    assert _bumps(db) == [(CASE, "closed")]


def test_losing_the_race_to_close_bumps_nothing():
    """rowcount 0 means another worker closed it and wrote its own bump."""
    db = _FakeDb(rowcount=0)

    assert trial_service.close_case(CASE, conn=db) == "already_done"
    assert _bumps(db) == []


@pytest.fixture
def juror(monkeypatch):
    """A juror who speaks, with the model and the panel stubbed out."""
    monkeypatch.setattr(
        trial_service.agents_service,
        "get_agent",
        lambda *a, **k: {"personality_prompt": "יבש", "guilt_bias": 0.5},
    )
    monkeypatch.setattr(trial_service, "_case_context", lambda *a, **k: {})
    monkeypatch.setattr(
        trial_service.brain,
        "deliberate",
        lambda *a, **k: {"vote": trial_service.decide.GUILTY, "line": "אשם."},
    )
    monkeypatch.setattr(
        trial_service.comments_service, "create_comment", lambda *a, **k: ("ok", 99)
    )
    monkeypatch.setattr(
        trial_service.memory_service, "record_event", lambda *a, **k: True
    )
    return {"id": 1, "case_id": CASE, "juror_user_id": SPEAKER}


def test_a_juror_speaking_bumps_the_case(monkeypatch, juror):
    monkeypatch.setattr(
        trial_service.jury_service, "record_speech", lambda *a, **k: "ok"
    )
    db = _FakeDb()

    assert trial_service.speak_as_juror(juror, conn=db) == "ok"
    assert _bumps(db) == [(CASE, "deliberation")]


def test_a_replayed_juror_tick_bumps_nothing(monkeypatch, juror):
    """already_done means the line on the record is another worker's."""
    monkeypatch.setattr(
        trial_service.jury_service, "record_speech", lambda *a, **k: "already_done"
    )
    db = _FakeDb()

    assert trial_service.speak_as_juror(juror, conn=db) == "already_done"
    assert _bumps(db) == []
