"""A bot may only file a case that a live model actually wrote.

Everything else the brain does fails open: a juror whose API call times out
still says something, because the alternative is a trial that stalls. A filing
is the one exception, and the reason is that it is *permanent and public*. The
offline generator picks its defendant from one fixed list, so an afternoon
with a dead backend does not make the feed a little duller - it fills it with
the same handful of lawsuits under different names.

These tests pin both halves of that: the filing path closes, and every other
path stays open.
"""

from __future__ import annotations

from types import SimpleNamespace

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
    """Credentialed, capable, and failing on every call - the outage."""
    monkeypatch.setenv("BRAIN_FORCE_OFFLINE", "0")
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("LLM_API_KEY", "test-key")

    def explode(*args, **kwargs):
        raise TimeoutError("the endpoint is down")

    monkeypatch.setattr(llm, "invent_lawsuit", explode)


@pytest.fixture
def incapable_backend(monkeypatch):
    """Credentialed and healthy, but unable to enforce a schema."""
    monkeypatch.setenv("BRAIN_FORCE_OFFLINE", "0")
    monkeypatch.setenv("LLM_PROVIDER", "gateway")
    monkeypatch.setenv("LLM_ENDPOINT", "https://example.invalid/prod/suggest")
    monkeypatch.setenv("LLM_API_KEY", "test-key")

    def unreachable(*args, **kwargs):  # pragma: no cover - the point is it is not called
        raise AssertionError("a filing was requested from a provider that cannot enforce one")

    monkeypatch.setattr(llm, "invent_lawsuit", unreachable)


# --- the brain seam ---------------------------------------------------------


def test_no_backend_configured_invents_nothing(offline_backend):
    assert brain.invent_lawsuit(PERSONALITY, "seed", require_llm=True) is None


def test_failed_call_invents_nothing(broken_backend):
    assert brain.invent_lawsuit(PERSONALITY, "seed", require_llm=True) is None


def test_the_failure_is_still_reported_to_health(broken_backend):
    brain.invent_lawsuit(PERSONALITY, "seed", require_llm=True)
    assert brain.LAST_CALL.snapshot()["last_error"].startswith("TimeoutError")


def test_a_provider_that_cannot_enforce_a_schema_is_never_asked(incapable_backend):
    """The gate is checked before the call, not after a bad answer.

    Without an enforced schema `defendant` is a suggestion, and the one rule
    the court cannot bend - a bot may never sue a person - is checked against
    exactly that field. A plausible unenforced filing is worse than none.
    """
    assert brain.invent_lawsuit(PERSONALITY, "seed", require_llm=True) is None


def test_the_missing_capability_is_named_rather_than_guessed_at(incapable_backend):
    """"Nothing was filed" and "the model failed" are different operator problems."""
    brain.invent_lawsuit(PERSONALITY, "seed", require_llm=True)
    snapshot = brain.LAST_CALL.snapshot()
    assert snapshot["missing_capability"] == "structured_output"
    assert snapshot["last_error"] is None


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
    """A database that records writes, and refuses to accept a case.

    Filing is the write under test, so an INSERT into `cases` is a hard failure
    rather than something to assert on afterwards - it fails at the line that
    caused it, with a stack trace pointing at the caller.

    Episodes are a different matter: `_file_case` writes one after a successful
    filing, and that write is correct. It is recorded so a test can look at it,
    which is also how the "nothing at all happened" case stays honest -
    `writes == []` covers every table, not just the one this class knows about.
    """

    def __init__(self) -> None:
        self.writes: list[str] = []

    def query_all(self, sql, params=()):
        return []

    def query_one(self, sql, params=()):
        return None

    def execute(self, sql, params=()):
        self.writes.append(sql)
        if "INTO cases" in sql:  # pragma: no cover - a failure marker
            raise AssertionError("a case was written with no model to write it")
        return SimpleNamespace(rowcount=1, lastrowid=1)


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
    # And the bot now remembers having filed it. A court personality that files
    # a lawsuit and has no memory of doing so is the failure the episode log
    # exists to close.
    assert any("INTO agent_events" in write for write in db.writes)
