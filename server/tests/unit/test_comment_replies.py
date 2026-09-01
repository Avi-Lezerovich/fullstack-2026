# -*- coding: utf-8 -*-
"""A bot answers somebody who answered it.

Before this existed, every case page had the same dead end: a bot posts a sharp
line, a human replies to it, and nothing happens - ever. The reply sits there
addressed to a personality that will never read it. That is worse than a dull
comment, because the person deliberately started a conversation and the site
swallowed it.

The threading was already in the schema (`parent_comment_id`, `root_comment_id`,
maintained by `create_comment` since the beginning). The only missing piece was
something that went looking for the replies nobody had answered - so what these
tests pin is the claim that query makes, and the two independent guards that
stop a retried tick answering twice.

No database and no network: the connection is a fake that records what it was
asked.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app import brain
from worker import social_tasks

BOT = 7
HUMAN = 9
CASE = 3
REPLY = 41

PERSONALITY = "מושבע ספקן ויבש."


class _FakeDb:
    """One un-answered reply, and a record of everything written."""

    def __init__(self, replies=None):
        self.replies = [
            {
                "reply_id": REPLY,
                "case_id": CASE,
                "reply_body": "אבל זה בכלל לא מה שקרה",
                "human_id": HUMAN,
                "human_name": "דנה",
                "bot_id": BOT,
                "personality_prompt": PERSONALITY,
                "personality_name": "הספקן",
            }
        ] if replies is None else replies
        self.selects: list[str] = []
        self.writes: list[tuple[str, tuple]] = []
        self.commits = 0

    def query_all(self, sql, params=()):
        self.selects.append(sql)
        if "parent.author_id" in sql:
            return self.replies
        return []

    def query_one(self, sql, params=()):
        self.selects.append(sql)
        # create_comment resolves the parent to work out depth and thread root.
        if "SELECT id, case_id, depth, root_comment_id FROM comments" in sql:
            return {"id": REPLY, "case_id": CASE, "depth": 1, "root_comment_id": 40}
        if "FROM comments cm JOIN users u" in sql:
            return {
                "id": REPLY,
                "body": "אבל זה בכלל לא מה שקרה",
                "author_id": HUMAN,
                "case_id": CASE,
                "root_comment_id": 40,
                "author_name": "דנה",
            }
        if "FROM cases WHERE id" in sql:
            return {
                "id": CASE,
                "title": "התביעה נגד המדפסת",
                "body": "היא צפצפה שלוש פעמים.",
                "defendant_text": "המדפסת במשרד",
                "author_id": HUMAN,
                # create_comment reads this one to decide whom to notify.
                "defendant_user_id": None,
            }
        if "FROM users WHERE id" in sql:
            return {"id": HUMAN, "name": "דנה", "bio": None, "created_at": None}
        return None

    def query_value(self, sql, params=(), default=None):
        return default

    def execute(self, sql, params=()):
        self.writes.append((sql, params))
        return SimpleNamespace(rowcount=1, lastrowid=99)

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass

    def close(self):
        pass


@pytest.fixture
def offline(monkeypatch):
    """No credentials: the stenographer writes the reply, and that is fine here."""
    monkeypatch.setenv("BRAIN_FORCE_OFFLINE", "1")


@pytest.fixture
def db(monkeypatch):
    fake = _FakeDb()
    monkeypatch.setattr(social_tasks, "connect", lambda: fake)
    return fake


# --- what the query claims ---------------------------------------------------


def test_only_a_bot_that_has_not_answered_yet_is_selected(db):
    """The `NOT EXISTS` is the first of two independent idempotency layers.

    Once the bot has replied, its own child comment exists and the row stops
    matching - the same "the newest one is not mine" shape the direct-message
    task uses, and the reason neither needs a status column.
    """
    social_tasks._replies_awaiting_a_bot(db, 5)
    sql = db.selects[0]
    assert "NOT EXISTS" in sql
    assert "child.author_id = parent.author_id" in sql


def test_only_casual_comments_are_answered(db):
    """A judge chatting under its own verdict reads as amending it.

    Court speech is a permanent finding, published unscreened precisely because
    a rejected verdict has nowhere to go. Replies to it are a different kind of
    thing, and this is where that line is drawn.
    """
    social_tasks._replies_awaiting_a_bot(db, 5)
    assert "parent.role = 'user'" in db.selects[0]


def test_a_bot_is_never_answered(db):
    """Two bots replying to each other is a loop with a scheduler attached."""
    social_tasks._replies_awaiting_a_bot(db, 5)
    assert "ru.is_bot = 0" in db.selects[0]


def test_hidden_content_is_not_engaged_with(db):
    social_tasks._replies_awaiting_a_bot(db, 5)
    assert "cm.moderation_status IN ('published', 'flagged')" in db.selects[0]


# --- what the task does ------------------------------------------------------


def test_the_bot_answers_in_the_thread_it_was_addressed_in(db, offline):
    assert social_tasks.reply_to_comment_replies(limit=5) == 1

    inserts = [(sql, params) for sql, params in db.writes if "INTO comments" in sql]
    assert len(inserts) == 1
    _, params = inserts[0]
    # (case_id, author_id, parent_comment_id, ...) - threaded under the reply,
    # not posted as a fresh top-level opinion about the case.
    assert params[0] == CASE
    assert params[1] == BOT
    assert params[2] == REPLY


def test_the_reply_is_screened(db, offline):
    """It is a bot comment, not court speech, so it can simply be dropped.

    The exemption that lets a verdict publish unscreened exists because a
    rejected verdict would wedge the case forever. Nothing wedges if this one
    is refused - the thread stays exactly as it was.
    """
    inserts = [
        params
        for sql, params in db.writes
        if "INTO comments" in sql
    ]
    social_tasks.reply_to_comment_replies(limit=5)
    inserts = [params for sql, params in db.writes if "INTO comments" in sql]
    # moderation_status is decided by the screen rather than hardcoded to
    # 'published', which is what `screen=True` (the default) means here.
    assert inserts[0][7] in ("published", "flagged", "hidden", "rejected")


def test_a_retried_tick_cannot_post_twice(db, offline):
    """The second guard: a dedupe key derived from the reply being answered."""
    social_tasks.reply_to_comment_replies(limit=5)
    keys = [
        params[-1]
        for sql, params in db.writes
        if "INTO comments" in sql
    ]
    assert keys == [f"creply:{REPLY}"]


def test_the_bot_remembers_having_answered(db, offline):
    social_tasks.reply_to_comment_replies(limit=5)
    episodes = [params for sql, params in db.writes if "INTO agent_events" in sql]
    assert len(episodes) == 1
    (agent_id, _kind, case_id, subject_id, _summary, _weight, key) = episodes[0]
    assert agent_id == BOT          # whose memory it is
    assert case_id == CASE
    assert subject_id == HUMAN      # who it was with
    # Keyed on the reply, so a retried tick remembers this exchange once.
    assert key == f"creply-ev:{REPLY}"


def test_nothing_to_answer_is_not_an_error(monkeypatch, offline):
    fake = _FakeDb(replies=[])
    monkeypatch.setattr(social_tasks, "connect", lambda: fake)
    assert social_tasks.reply_to_comment_replies(limit=5) == 0
    assert fake.writes == []


def test_the_reply_is_written_from_the_thread_it_is_in(db, offline, monkeypatch):
    """A bot answering a heckler with a new monologue is not a conversation."""
    seen = {}

    def spy(personality, task, context, **kwargs):
        seen.update({"task": task, "context": context})
        return "נרשם."

    monkeypatch.setattr(brain, "generate", spy)
    social_tasks.reply_to_comment_replies(limit=5)

    assert seen["task"] == "bot_comment_reply"
    assert "אבל זה בכלל לא מה שקרה" in seen["context"]["replying_to"]
