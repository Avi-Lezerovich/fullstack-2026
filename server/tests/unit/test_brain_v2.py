# -*- coding: utf-8 -*-
"""The parts of brain v2 that fail silently rather than loudly.

Everything here is a fake or a pure function - no database, no network - so it
runs in a bare checkout with nothing configured, which is the same bar the rest
of this suite holds.

The theme is the same throughout: each of these breaks without raising. A cache
that stops being read still returns correct answers, just dearer. A provider
that cannot enforce a schema still returns plausible JSON. A juror whose vote
disagrees with its own argument still produces a valid trial. None of them
would ever show up as an exception, so each one gets an assertion instead.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app import brain
from app.brain import llm
from app.services import memory_service

PERSONALITY = "שופט קפדן שסופר פסיקים."
OTHER = "מושבעת שמצטטת סעיפים שלא קיימים."


# --- the prompt is ordered for caching --------------------------------------


def test_the_shared_prefix_is_byte_identical_across_characters():
    """The whole caching design rests on this one property.

    Prompt caching is a prefix match, so the first block has to be the same
    bytes for every personality and every task or there is no shared prefix to
    cache at all. The previous version put the character sheet between the two
    shared halves, which reads well and meant no two calls in the application
    ever shared a prefix.
    """
    assert llm.build_system(PERSONALITY)[0] == llm.build_system(OTHER)[0]


def test_the_shared_block_comes_first_and_the_character_last():
    blocks = llm.build_system(PERSONALITY)
    assert PERSONALITY in blocks[1]["text"]
    assert PERSONALITY not in blocks[0]["text"]


def test_both_stable_blocks_carry_a_breakpoint():
    """Two, and only two: the API allows four and the third block is volatile."""
    blocks = llm.build_system(PERSONALITY)
    assert all("cache_control" in block for block in blocks)
    assert len(blocks) == 2


def test_the_situation_block_is_never_cached():
    """It changes every call, so a breakpoint there is a pure surcharge.

    The signature of getting this wrong is a cache write on every request and a
    read that never covers the shared prefix - which costs money silently and
    looks like working caching from the outside.
    """
    blocks = llm.build_system(PERSONALITY, situation="מה שקורה עכשיו")
    assert len(blocks) == 3
    assert "cache_control" not in blocks[2]


def test_nothing_volatile_leaks_into_the_shared_block():
    """A timestamp or an id here would invalidate the cache for the whole app."""
    first = llm.build_system(PERSONALITY)[0]["text"]
    second = llm.build_system(PERSONALITY)[0]["text"]
    assert first == second
    assert "20" not in first.replace("2026", "")  # no interpolated year/date


def test_effort_is_pinned_per_task():
    """Varying effort within a route invalidates the messages cache every call."""
    assert llm.effort_for("jury_deliberation") == llm.effort_for("jury_deliberation")
    assert llm.effort_for("verdict") == "medium"
    assert llm.effort_for("bot_comment") == "low"


def test_thinking_has_room_to_think():
    """Thinking tokens are billed against max_tokens.

    At the old floor of 512 the model spent the budget reasoning, returned no
    text blocks, and every 240-character task on the site - bot comments,
    private replies - fell through to the phrase bank without logging a thing.
    """
    assert llm._max_tokens_for(240) >= 2048


# --- a refusal is an answer, not a blip -------------------------------------


def test_a_refusal_is_reported_as_a_refusal():
    """Current models decline with HTTP 200 and no text blocks.

    Without this the refusal is indistinguishable from a timeout: both produce
    an empty string, both fall back, and health reports "empty completion" for
    a request that was answered perfectly clearly.
    """
    message = SimpleNamespace(
        stop_reason="refusal",
        stop_details=SimpleNamespace(category="cyber"),
        content=[],
    )
    with pytest.raises(ValueError, match="refused"):
        llm._text_of(message)


def test_an_ordinary_answer_is_not_mistaken_for_one():
    message = SimpleNamespace(
        stop_reason="end_turn",
        stop_details=None,
        content=[SimpleNamespace(type="text", text=" נרשם ")],
    )
    assert llm._text_of(message) == "נרשם"


# --- the vote and the argument are one act ----------------------------------


class _FakeProvider:
    """A provider that answers with whatever the test hands it."""

    def __init__(self, payload, *, boom=None):
        self.payload = payload
        self.boom = boom
        self.calls = 0
        self.output_format = None

    def complete(self, system, messages, **kwargs):
        self.calls += 1
        self.output_format = kwargs.get("output_format")
        if self.boom:
            raise self.boom
        return llm.Completion(text=self.payload, cache_read=7, cache_write=3)


@pytest.fixture
def capable(monkeypatch):
    monkeypatch.setenv("BRAIN_FORCE_OFFLINE", "0")
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("LLM_API_KEY", "test-key")

    def install(fake):
        monkeypatch.setattr(
            llm,
            "PROVIDERS",
            {
                **llm.PROVIDERS,
                "anthropic": llm.Provider(
                    complete=fake.complete,
                    is_configured=lambda settings: True,
                    default_model="claude-opus-5",
                    capabilities=llm.SDK_CAPABILITIES,
                ),
            },
        )
        return fake

    return install


CASE = {"case_title": "כרית", "defendant": "המדפסת", "charges": ["גרימת עייפות"]}


def test_the_model_decides_and_the_line_comes_with_it(capable):
    fake = capable(
        _FakeProvider(json.dumps({"vote": "not_guilty", "line": "ומה זה מוכיח."}))
    )
    spoken = brain.deliberate(
        PERSONALITY, CASE, guilt_bias=0.9, case_id=1, juror_user_id=2
    )

    assert spoken["vote"] == "not_guilty"
    assert spoken["line"] == "ומה זה מוכיח."
    # One call, not two: the argument and the decision are the same turn, which
    # is what makes them incapable of disagreeing.
    assert fake.calls == 1
    # And the enum is enforced by the API rather than hoped for - this is the
    # difference between a schema and a suggestion.
    assert fake.output_format is llm.DELIBERATION_SCHEMA


def test_a_vote_outside_the_enum_is_refused(capable):
    """A vote of "maybe" would be tallied as neither and vanish from the count."""
    capable(_FakeProvider(json.dumps({"vote": "maybe", "line": "אולי"})))
    spoken = brain.deliberate(
        PERSONALITY, CASE, guilt_bias=0.9, case_id=1, juror_user_id=2
    )
    # Fell through to the dial, which can only answer guilty or not_guilty.
    assert spoken["vote"] in ("guilty", "not_guilty")
    assert spoken["line"]


def test_the_dial_still_decides_with_no_model(monkeypatch):
    """The zero-credential path is unchanged, and still reproducible."""
    monkeypatch.setenv("BRAIN_FORCE_OFFLINE", "1")
    first = brain.deliberate(PERSONALITY, CASE, guilt_bias=0.9, case_id=1, juror_user_id=2)
    second = brain.deliberate(PERSONALITY, CASE, guilt_bias=0.9, case_id=1, juror_user_id=2)
    assert first == second
    assert first["vote"] in ("guilty", "not_guilty")


def test_the_fallback_tells_the_juror_which_way_it_voted(monkeypatch):
    """Otherwise the fallback reproduces the original bug in miniature.

    The whole reason `deliberate` returns both halves is that a juror arguing
    one way while being counted the other is the defect being fixed. On the
    fallback path something else picks the vote, so it has to be handed to the
    prose - and `your_vote` is how.
    """
    monkeypatch.setenv("BRAIN_FORCE_OFFLINE", "1")
    seen = {}

    def spy(personality, task, context, **kwargs):
        seen.update(context)
        return "נרשם."

    monkeypatch.setattr(brain, "generate", spy)
    spoken = brain.deliberate(PERSONALITY, CASE, guilt_bias=0.9, case_id=1, juror_user_id=2)
    assert seen["your_vote"] == spoken["vote"]


def test_a_provider_that_cannot_enforce_the_enum_uses_the_dial(monkeypatch):
    monkeypatch.setenv("BRAIN_FORCE_OFFLINE", "0")
    monkeypatch.setenv("LLM_PROVIDER", "gateway")
    monkeypatch.setenv("LLM_ENDPOINT", "https://example.invalid/x")
    monkeypatch.setenv("LLM_API_KEY", "k")

    def unreachable(*a, **kw):  # pragma: no cover - the point is it is not called
        raise AssertionError("a vote was asked of a provider that cannot enforce one")

    monkeypatch.setattr(llm, "deliberate", unreachable)
    spoken = brain.deliberate(PERSONALITY, CASE, guilt_bias=0.5, case_id=1, juror_user_id=2)
    assert spoken["vote"] in ("guilty", "not_guilty")


def test_the_disposition_is_a_phrase_not_a_number():
    """Handing a model "0.75" gets jurors announcing their own hit rate."""
    phrase = llm.disposition_of(0.75)
    assert phrase and "0.75" not in phrase and "75" not in phrase


# --- the cache counters reach the health endpoint ----------------------------


def test_cache_activity_is_counted(capable):
    """Caching fails silently; the usage counters are the only ground truth."""
    capable(_FakeProvider("נרשם."))
    before = brain.LAST_CALL.snapshot()["cache_reads"]
    brain.generate(PERSONALITY, "bot_comment", CASE)
    after = brain.LAST_CALL.snapshot()
    assert after["cache_reads"] == before + 7
    assert after["last_backend"] == "llm"


# --- episodes ----------------------------------------------------------------


class _RecordingDb:
    def __init__(self, rowcount=1):
        self.statements = []
        self.rowcount = rowcount

    def execute(self, sql, params=()):
        self.statements.append((sql, params))
        return SimpleNamespace(rowcount=self.rowcount, lastrowid=1)

    def query_all(self, sql, params=()):
        self.statements.append((sql, params))
        return []


def test_an_episode_carries_the_weight_of_what_happened():
    db = _RecordingDb()
    memory_service.record_event(7, "verdict", "פסקת בתיק.", conn=db)
    _, params = db.statements[0]
    assert params[5] == memory_service.EVENT_IMPORTANCE["verdict"]

    db = _RecordingDb()
    memory_service.record_event(7, "like", "לייק.", conn=db)
    assert db.statements[0][1][5] == memory_service.EVENT_IMPORTANCE["like"]


def test_an_unknown_kind_still_gets_a_sane_weight():
    """A new episode kind must not need a schema change or a corpus entry."""
    db = _RecordingDb()
    memory_service.record_event(7, "something_new", "קרה משהו.", conn=db)
    assert db.statements[0][1][5] == memory_service.DEFAULT_IMPORTANCE


def test_a_retried_tick_does_not_double_remember():
    """The upsert reports 0 rows, and that is not an error."""
    db = _RecordingDb(rowcount=0)
    assert memory_service.record_event(7, "vote", "הצבעת.", dedupe_key="vote:1", conn=db) is False
    assert "ON DUPLICATE KEY UPDATE" in db.statements[0][0]


def test_an_empty_episode_is_not_written():
    db = _RecordingDb()
    assert memory_service.record_event(7, "vote", "   ", conn=db) is False
    assert db.statements == []


def test_retrieval_never_matches_null_against_null():
    """`<=>` here would boost every episode with no case attached.

    NULL-safe equality reads as the obvious thing to use and does exactly the
    wrong thing: asked for "nothing in particular", it would rank the episodes
    least connected to the moment highest.
    """
    db = _RecordingDb()
    memory_service.recall_for_agent(7, case_id=None, conn=db)
    sql, _ = db.statements[0]
    assert "<=>" not in sql
    assert "IS NOT NULL AND case_id = %s" in sql


def test_relevance_ranks_the_same_case_above_the_same_person():
    assert memory_service._RELEVANCE_SAME_CASE > memory_service._RELEVANCE_SAME_PARTY


def test_recall_scores_by_all_three_terms():
    db = _RecordingDb()
    memory_service.recall_for_agent(7, case_id=3, subject_user_id=9, conn=db)
    sql, _ = db.statements[0]
    assert "importance" in sql and "EXP(" in sql and "CASE" in sql


# --- forgetting is complete ---------------------------------------------------


def test_forget_clears_every_table_that_names_the_person():
    """Three tables, and a half-working "forget me" is worse than none.

    `bot_memories` is included because a deployment mid-migration has rows in
    both stores, and `agent_events` because "the judge who sentenced you still
    brings it up" is exactly what somebody asking to be forgotten means.
    """
    db = _RecordingDb()
    memory_service.forget(9, conn=db)
    tables = " ".join(sql for sql, _ in db.statements)
    for table in ("agent_memories", "bot_memories", "agent_events"):
        assert table in tables
