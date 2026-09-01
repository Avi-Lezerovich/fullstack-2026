"""A bot may only file a case that a live model actually wrote.

Everything else the brain does fails open: a juror whose API call times out
still says something, because the alternative is a trial that stalls. A filing
is the one exception, and the reason is that it is *permanent and public*. The
offline generator picks its defendant from a fixed list of twelve, so an
afternoon with a dead backend does not make the feed a little duller - it fills
it with the same lawsuit under a dozen different names.

These tests pin both halves of that: the filing path closes, and every other
path stays open.
"""

from __future__ import annotations

import pytest

from app import brain
from app.brain import llm
from worker import social_tasks

PERSONALITY = "[tone:deadpan] שופט קפדן שסופר פסיקים."


@pytest.fixture
def offline_backend(monkeypatch):
    monkeypatch.setenv("BRAIN_FORCE_OFFLINE", "1")


@pytest.fixture
def broken_backend(monkeypatch):
    """Credentialed, and failing on every call - the outage this is about."""
    monkeypatch.setenv("BRAIN_FORCE_OFFLINE", "0")
    monkeypatch.setenv("LLM_PROVIDER", "gateway")
    monkeypatch.setenv("LLM_ENDPOINT", "https://example.invalid/prod/suggest")
    monkeypatch.setenv("LLM_API_KEY", "test-key")

    def explode(*args, **kwargs):
        raise TimeoutError("the endpoint is down")

    monkeypatch.setattr(llm, "invent_lawsuit", explode)


# --- the brain seam ---------------------------------------------------------


def test_no_backend_configured_invents_nothing(offline_backend):
    assert brain.invent_lawsuit(PERSONALITY, "seed", require_llm=True) is None


def test_failed_call_invents_nothing(broken_backend):
    assert brain.invent_lawsuit(PERSONALITY, "seed", require_llm=True) is None


def test_the_failure_is_still_reported_to_health(broken_backend):
    brain.invent_lawsuit(PERSONALITY, "seed", require_llm=True)
    assert brain.LAST_CALL.snapshot()["last_error"].startswith("TimeoutError")


def test_the_default_still_falls_back(offline_backend):
    """Callers that did not ask for the strict contract keep the old one."""
    filing = brain.invent_lawsuit(PERSONALITY, "seed")
    assert filing is not None
    assert filing["title"] and filing["defendant_text"] and filing["charges"]


def test_every_other_task_still_fails_open(offline_backend):
    """A juror still speaks with no backend. Only filings are strict."""
    assert brain.generate(PERSONALITY, "jury_deliberation", {"case_title": "x"})


# --- the worker -------------------------------------------------------------


class _StubDb:
    """A database that would notice being written to."""

    def __init__(self) -> None:
        self.writes: list[str] = []

    def query_all(self, sql, params=()):
        return []

    def query_one(self, sql, params=()):
        return None

    def execute(self, sql, params=()):  # pragma: no cover - a failure marker
        self.writes.append(sql)
        raise AssertionError("a case was written with no model to write it")


def test_the_bot_files_nothing_at_all(offline_backend):
    db = _StubDb()
    bot = {"user_id": 7, "personality_prompt": PERSONALITY, "personality_name": "השופט"}

    assert social_tasks._file_case(db, bot, tick=3) is False
    assert db.writes == []


def test_the_bot_still_files_when_the_model_answers(monkeypatch, offline_backend):
    """The guard is about the backend, not about filing in general."""
    monkeypatch.setattr(
        brain,
        "invent_lawsuit",
        lambda *a, **kw: {
            "title": "התביעה נגד המדפסת",
            "defendant_text": "המדפסת במשרד",
            "charges": ["הפרעה לסדר הציבורי"],
            "body": "היא צפצפה.",
        },
    )
    created: dict = {}

    def fake_create_case(author_id, title, body, defendant_text, **kwargs):
        created.update({"author_id": author_id, "title": title})
        return "ok", 42

    monkeypatch.setattr(social_tasks.cases_service, "create_case", fake_create_case)

    db = _StubDb()
    bot = {"user_id": 7, "personality_prompt": PERSONALITY, "personality_name": "השופט"}

    assert social_tasks._file_case(db, bot, tick=3) is True
    assert created["author_id"] == 7
