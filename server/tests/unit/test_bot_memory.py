"""The bot remembers who it is talking to, and what it already said.

Three layers, and each one failed in its own visible way before it existed:

  * no grounded facts  -> a juror asking somebody whether they had ever filed
    a case, in the middle of that person's own trial;
  * no window          -> the same bot answering its own previous message as
    though a stranger had sent it;
  * no stored summary  -> a correspondence that reset every twelve messages.

Nothing here touches a database or a network. The layers are assembled from
plain rows, which is exactly the seam these tests hold still.
"""

from __future__ import annotations

import json

import pytest

from app import brain
from app.brain import llm
from app.services import memory_service

BOT = 7
HUMAN = 9
PERSONALITY = "[tone:deadpan] שופט קפדן שסופר פסיקים."


def _msg(id_, sender, body):
    return {"id": id_, "sender_id": sender, "body": body}


# --- layer 2: the window as turns -------------------------------------------


def test_the_bot_reads_its_own_lines_as_its_own():
    turns = memory_service._turns(
        [_msg(1, HUMAN, "שלום"), _msg(2, BOT, "שלום לך"), _msg(3, HUMAN, "שאלה")], BOT
    )
    assert [turn["role"] for turn in turns] == ["user", "assistant", "user"]
    assert turns[1]["content"] == "שלום לך"


def test_two_messages_from_one_side_become_one_turn():
    """A transcript that alternates is the one every chat model was trained on."""
    turns = memory_service._turns(
        [_msg(1, HUMAN, "שלום"), _msg(2, HUMAN, "עוד משהו")], BOT
    )
    assert len(turns) == 1
    assert turns[0]["content"] == "שלום\nעוד משהו"


def test_empty_bodies_are_not_turns():
    assert memory_service._turns([_msg(1, HUMAN, "   ")], BOT) == []


# --- layer 3: when to rewrite the stored memory ------------------------------


def _recall(rows, *, total, covered):
    return {
        "messages": rows,
        "total_messages": total,
        "memory": {"summary": "", "facts": [], "covered_event_id": covered},
    }


def test_a_short_conversation_is_its_own_memory():
    """While it all still fits in the window, a summary would be a worse copy."""
    rows = [_msg(i, HUMAN, "x") for i in range(1, 5)]
    assert memory_service._is_stale(_recall(rows, total=4, covered=0)) is False


def test_a_long_conversation_is_summarised_once_it_overflows():
    rows = [_msg(i, HUMAN, "x") for i in range(20, 32)]
    assert memory_service._is_stale(_recall(rows, total=40, covered=0)) is True


def test_what_is_already_remembered_is_not_summarised_again():
    rows = [_msg(i, HUMAN, "x") for i in range(20, 32)]
    assert memory_service._is_stale(_recall(rows, total=40, covered=25)) is False


def test_the_transcript_names_both_sides():
    text = memory_service.transcript([_msg(1, HUMAN, "שלום"), _msg(2, BOT, "כן")], BOT)
    assert text == "הוא: שלום\nאתה: כן"


# --- layer 3: what may be stored --------------------------------------------


class _CapturingDb:
    def __init__(self):
        self.params = None

    def execute(self, sql, params=()):
        self.params = params
        return None


def test_a_memory_cannot_grow_until_it_is_the_prompt():
    """It is sent with every single reply, so the cap is a prompt budget."""
    db = _CapturingDb()
    memory_service.save_memory(
        BOT,
        HUMAN,
        summary="א" * 5000,
        facts=[f"עובדה {i}" for i in range(50)],
        covered_event_id=12,
        conn=db,
    )
    _, _, summary, facts, _ = db.params
    assert len(summary) == memory_service.SUMMARY_MAX_CHARS
    assert len(json.loads(facts)) == memory_service.MAX_FACTS


@pytest.mark.parametrize("stored", ['["גר בחיפה"]', ["גר בחיפה"]])
def test_facts_survive_either_json_shape(stored):
    """PyMySQL hands back a JSON column as a string on some pairings, a list on others."""
    assert memory_service._facts_of(stored) == ["גר בחיפה"]


def test_a_broken_facts_column_is_no_facts_rather_than_a_crash():
    assert memory_service._facts_of("{not json") == []


# --- the memory actually reaches the model -----------------------------------


def test_what_the_bot_knows_is_in_the_prompt():
    prompt = llm.build_prompt(
        "bot_reply",
        {
            "about_them": "שם: דנה",
            "their_cases": ['"התביעה נגד יום שני" נגד יום שני (חויב)'],
            "you_remember": "היא סיפרה שהיא עוברת דירה",
            "you_know": ["גרה בחיפה"],
        },
    )
    for marker in ("דנה", "יום שני", "עוברת דירה", "גרה בחיפה"):
        assert marker in prompt


def test_a_juror_is_told_what_the_room_already_said():
    prompt = llm.build_prompt(
        "jury_deliberation", {"case_title": "כרית", "discussion": ["השופט: כבר נאמר"]}
    )
    assert "כבר נאמר" in prompt


class _FakeProvider:
    """Records what the provider layer was actually handed."""

    def __init__(self):
        self.system = None
        self.messages = None

    def complete(
        self,
        system,
        messages,
        *,
        model,
        max_tokens,
        effort,
        output_format=None,
        stream=False,
    ):
        self.system = system
        self.messages = messages
        self.effort = effort
        return llm.Completion(text="תשובה", cache_read=11, cache_write=22)

    @property
    def system_text(self):
        """The blocks, as the one string they used to be."""
        return "\n\n".join(block["text"] for block in self.system)


@pytest.fixture
def provider(monkeypatch):
    fake = _FakeProvider()
    monkeypatch.setenv("BRAIN_FORCE_OFFLINE", "0")
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
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


def test_the_conversation_is_sent_as_turns(provider):
    history = [
        {"role": "user", "content": "שאלתי אותך משהו"},
        {"role": "assistant", "content": "ועניתי"},
        {"role": "user", "content": "אז מה עכשיו"},
    ]
    brain.generate(PERSONALITY, "bot_reply", {"about_them": "שם: דנה"}, history=history)

    assert provider.messages == history
    # The brief and the memory ride in the system prompt, so the turns stay a
    # clean alternating conversation and the human's own text is never mixed
    # with instructions addressed to the model.
    assert "דנה" in provider.system_text
    assert provider.messages[-1]["content"] == "אז מה עכשיו"


def test_without_history_it_is_still_one_user_turn(provider):
    """Every other task must be unchanged by the existence of conversations."""
    brain.generate(PERSONALITY, "bot_comment", {"case_title": "כרית"})

    assert len(provider.messages) == 1
    assert provider.messages[0]["role"] == "user"
    assert "כרית" in provider.messages[0]["content"]


# --- and a memory is never invented ------------------------------------------


def test_no_model_means_no_memory(monkeypatch):
    """The offline generator writes from a phrase bank. A phrase bank must not
    be allowed to write facts about a real person."""
    monkeypatch.setenv("BRAIN_FORCE_OFFLINE", "1")
    assert brain.remember(PERSONALITY, {"transcript": "הוא: שלום"}) is None


def test_a_failed_rewrite_leaves_the_old_memory_standing(provider, monkeypatch):
    def explode(*args, **kwargs):
        raise TimeoutError("the endpoint is down")

    monkeypatch.setattr(llm, "remember", explode)
    assert brain.remember(PERSONALITY, {"transcript": "הוא: שלום"}) is None
    assert brain.LAST_CALL.snapshot()["last_error"].startswith("TimeoutError")


# --- layer 1: the case a comment is actually about ---------------------------
#
# The bug this closes, in full: an idle bot was handed a case TITLE and the
# defendant's name, and nothing else. Asked to comment, the model did the only
# thing it could and invented the rest - a filing about a dog's lost pillow
# produced a confident comment about somebody's laundry. It was not a
# hallucination so much as an honest answer to the question it was asked.


class _FakeCaseDb:
    """A database of exactly one case, answering by which query it recognises."""

    ROWS = {
        "case": {
            "id": 3,
            "title": "תביעה על סך 4 עצמות, כרית אחת ופיצוי בגין עוגמת נפש",
            "body": "התובע, בלייק, הוא כלב תושב הבית. הנתבע פרסם תמונות משפילות.",
            "defendant_text": "Avi",
            "author_id": HUMAN,
            "status": "jury_deliberation",
            "verdict": None,
            "author_name": "Blake",
        },
    }

    def query_one(self, sql, params=()):
        if "FROM cases c JOIN users u" in sql:
            return self.ROWS["case"]
        if "FROM users WHERE id" in sql:
            return {"id": HUMAN, "name": "Blake", "bio": "כלב", "created_at": None}
        if "FROM agent_memories" in sql:
            return {"summary": "הוא כלב", "facts": '["ישן על הגב"]', "covered_event_id": 4}
        return None

    def query_all(self, sql, params=()):
        if "case_charges" in sql:
            return [{"charge": "הפרת אמון"}]
        if "SELECT cm.body, u.name AS author_name" in sql:
            return [{"body": "בנוסף הנתבע הבטיח לי חטיף", "author_name": "Blake"}]
        if "SELECT body FROM comments" in sql:
            return [{"body": "אמרתי את זה כבר פעם אחת"}]
        if "JOIN cases c ON c.id = cm.case_id" in sql:
            return []
        if "WHERE author_id = %s AND moderation_status" in sql:
            return [
                {
                    "title": "תביעה על סך 4 עצמות",
                    "defendant_text": "Avi",
                    "status": "jury_deliberation",
                    "verdict": None,
                }
            ]
        return []

    def query_value(self, sql, params=(), default=None):
        return default


def test_a_commenting_bot_is_given_the_filing_itself():
    context = memory_service.recall_case(3, BOT, conn=_FakeCaseDb())["context"]

    # The things it used to invent, because it had never been shown them.
    assert "בלייק" in context["case_body"]
    assert context["plaintiff"] == "Blake"
    assert context["charges"] == ["הפרת אמון"]
    # What the thread already contains, and what this bot itself already said -
    # the two inputs that stop it repeating an observation somebody made an
    # hour ago.
    assert context["discussion"] == ["Blake: בנוסף הנתבע הבטיח לי חטיף"]
    assert context["you_already_said"] == ["אמרתי את זה כבר פעם אחת"]
    # And what it remembers about the person who filed it.
    assert context["you_remember"] == "הוא כלב"
    assert context["you_know"] == ["ישן על הגב"]


def test_the_filing_survives_all_the_way_into_the_prompt():
    context = memory_service.recall_case(3, BOT, conn=_FakeCaseDb())["context"]
    prompt = llm.build_prompt("bot_comment", context)

    assert "בלייק" in prompt
    assert "הפרת אמון" in prompt
    assert "אמרתי את זה כבר פעם אחת" in prompt


def test_a_missing_case_is_not_a_crash():
    class _Empty(_FakeCaseDb):
        def query_one(self, sql, params=()):
            return None

    assert memory_service.recall_case(999, BOT, conn=_Empty()) == {}


# --- the offline generator still has to answer the message it was sent -------


def test_offline_replies_change_when_the_conversation_does(monkeypatch):
    """The phrase bank cannot read - but it must not repeat itself either.

    Its variety is a hash of its inputs, and the memory context is stable
    across a thread. Without the turns in the seed, every reply in a
    conversation would be byte-identical to the first one.
    """
    monkeypatch.setenv("BRAIN_FORCE_OFFLINE", "1")
    context = {"about_them": "שם: דנה"}

    first = brain.generate(
        PERSONALITY, "bot_reply", context, history=[{"role": "user", "content": "שלום"}]
    )
    second = brain.generate(
        PERSONALITY,
        "bot_reply",
        context,
        history=[
            {"role": "user", "content": "שלום"},
            {"role": "assistant", "content": first},
            {"role": "user", "content": "ומה לגבי התיק שלי"},
        ],
    )
    assert first and second and first != second


def test_offline_replies_are_still_reproducible(monkeypatch):
    monkeypatch.setenv("BRAIN_FORCE_OFFLINE", "1")
    history = [{"role": "user", "content": "שלום"}]
    once = brain.generate(PERSONALITY, "bot_reply", {}, history=history)
    twice = brain.generate(PERSONALITY, "bot_reply", {}, history=history)
    assert once == twice
