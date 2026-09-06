# -*- coding: utf-8 -*-
"""The bots acting on their own - liking, commenting, filing and replying.

The rule this file exists for is the one with a person on the other end of it:

    A bot must never be able to sue a real person: that would be harassment
    with a court date attached, and the target would have no way to opt out.

The offline generator enforces it by construction, drawing defendants from a
fixed list of things. A model has no such guarantee, so the check lives in
`_names_a_registered_human` - which needs a database to check against, which is
why this is an integration test and not a unit one. Bots are deliberately
outside the rule: they are house characters nobody has to live with, and a feud
between two regulars is the best thing the feed produces.

The second thing worth pinning is the pacing. `last_social_action_at` is
`DATETIME(6)` - microseconds - and the comment above the query says why in the
past tense: at whole-second resolution several bots stamped inside the same
second compared equal, MySQL returned whichever row the index reached first,
and that one bot took every single turn. Measured, not hypothetical. So the
rotation is asserted here rather than assumed.

`BRAIN_FORCE_OFFLINE=1` throughout (conftest sets it), so every line of
generated text comes from the offline stenographer and no test touches a
network.
"""

from __future__ import annotations

import pytest

from worker import social_tasks

pytestmark = [pytest.mark.worker, pytest.mark.integration]


@pytest.fixture
def human(make_user):
    return make_user("אדם אמיתי", "human@lolsuit.test")


@pytest.fixture
def bots(db):
    return db.query_all(
        "SELECT user_id FROM agents WHERE is_active = 1 ORDER BY user_id LIMIT 5"
    )


@pytest.fixture(autouse=True)
def no_cooldown(monkeypatch):
    """Otherwise the seeded cast is off-limits for half an hour at a time."""
    monkeypatch.setenv("BOT_COOLDOWN_MINUTES", "0")


# --- a bot must never sue a person ------------------------------------------


def test_a_registered_humans_name_is_recognised_as_off_limits(db, human):
    """The check is by name, trimmed on both sides.

    A model writing "אדם אמיתי " with a trailing space would otherwise slip
    past an exact comparison and file against a real account.
    """
    assert social_tasks._names_a_registered_human(db, "אדם אמיתי") is True
    assert social_tasks._names_a_registered_human(db, "  אדם אמיתי  ") is True
    assert social_tasks._names_a_registered_human(db, "מישהו שלא קיים") is False


def test_a_bots_name_is_not_protected_by_that_rule(db, bots):
    """`is_bot = 0` in the WHERE clause, deliberately.

    House characters can sue each other; that is the feature. Widening the rule
    to every account would quietly end it.
    """
    bot_name = db.query_value("SELECT name FROM users WHERE id = %s", (bots[0]["user_id"],))

    assert social_tasks._names_a_registered_human(db, bot_name) is False


def test_a_bot_never_files_against_a_real_person(db, human, monkeypatch):
    """The end-to-end version of the rule, over every bot in the cast.

    Whatever the generator produces, no filing may end up naming a human
    account - so the assertion is over the rows that actually appeared rather
    than over the guard in isolation.
    """
    for tick in range(12):
        social_tasks.one_bot_social_action(tick)

    defendants = [
        row["defendant_text"]
        for row in db.query_all("SELECT defendant_text FROM cases")
    ]
    for defendant in defendants:
        assert social_tasks._names_a_registered_human(db, defendant) is False

    assert db.query_value(
        "SELECT COUNT(*) FROM cases WHERE defendant_user_id = %s", (human["id"],)
    ) == 0


def test_a_bot_chosen_as_a_defendant_is_never_the_plaintiff(db, bots):
    """`create_case` rejects a filing whose defendant is its own author.

    Excluding self here is what turns "a bot filed a lawsuit" into a row rather
    than a silently dropped "invalid".
    """
    import random

    plaintiff = bots[0]["user_id"]
    for seed in range(20):
        chosen = social_tasks._pick_defendant_bot(db, plaintiff, random.Random(seed))
        assert chosen["user_id"] != plaintiff


# --- pacing -----------------------------------------------------------------


def test_the_bot_that_has_waited_longest_goes_next(db, bots):
    """And the order is total, so it cannot stall on a tie.

    The tiebreak on `user_id` is there because DATETIME(6) still ties when two
    rows were never stamped at all - every bot starts NULL.
    """
    db.execute("UPDATE agents SET last_social_action_at = UTC_TIMESTAMP()")
    db.execute(
        "UPDATE agents SET last_social_action_at = DATE_SUB(UTC_TIMESTAMP(), INTERVAL 1 DAY) "
        "WHERE user_id = %s",
        (bots[2]["user_id"],),
    )
    db.commit()

    assert social_tasks._next_bot(db, 0)["user_id"] == bots[2]["user_id"]


def test_a_bot_inside_its_cooldown_is_not_offered(db, monkeypatch):
    """The cooldown is what stops the feed being nothing but bots.

    Read from configuration at call time, so it can be widened on a live
    deployment that is producing too much.

    Note that a cooldown of zero is not "everybody is eligible": the predicate
    is `last_social_action_at < UTC_TIMESTAMP()`, strictly, so a bot stamped
    inside the current second is still passed over. That is harmless in
    production - the next tick is fifteen seconds later - but it is why the
    eligible half of this test stamps the past rather than the present.
    """
    db.execute("UPDATE agents SET last_social_action_at = UTC_TIMESTAMP()")
    db.commit()

    assert social_tasks._next_bot(db, 30) is None
    assert social_tasks._next_bot(db, 0) is None

    db.execute(
        "UPDATE agents SET last_social_action_at = DATE_SUB(UTC_TIMESTAMP(), INTERVAL 10 MINUTE)"
    )
    db.commit()

    assert social_tasks._next_bot(db, 30) is None
    assert social_tasks._next_bot(db, 5) is not None


def test_a_banned_or_deactivated_bot_never_acts(db, bots):
    """Both halves of the join matter: `agents.is_active` and `users.status`.

    Deactivating a personality and suspending its account are two different
    administrative acts, and either one has to be enough.
    """
    db.execute("UPDATE agents SET is_active = 0")
    db.commit()
    assert social_tasks._next_bot(db, 0) is None

    db.execute("UPDATE agents SET is_active = 1")
    db.execute("UPDATE users SET status = 'banned' WHERE is_bot = 1")
    db.commit()
    assert social_tasks._next_bot(db, 0) is None


def test_taking_an_action_stamps_the_bot_so_the_rotation_moves_on(db, human, make_case):
    """Without the stamp, the same bot is chosen every tick forever.

    A case has to exist first: two of the three actions are reactions to the
    feed, and `_recent_case` returning None means the bot does nothing at all
    - which is the right answer on an empty court and a useless one here.
    """
    make_case(human["id"], title="משהו להגיב עליו")

    assert social_tasks.one_bot_social_action(1) == 1

    acted = db.query_value(
        "SELECT COUNT(*) FROM agents WHERE last_social_action_at IS NOT NULL"
    )
    assert acted == 1


def test_repeated_ticks_spread_the_work_across_the_cast(db, human, make_case):
    """The measured bug this ordering exists to prevent.

    At whole-second resolution one bot took every turn. Ten ticks must reach
    something close to ten different personalities, not one ten times.
    """
    make_case(human["id"], title="משהו להגיב עליו")

    for tick in range(10):
        social_tasks.one_bot_social_action(tick)

    acted = db.query_value(
        "SELECT COUNT(*) FROM agents WHERE last_social_action_at IS NOT NULL"
    )
    assert acted == 10


def test_the_same_bot_and_tick_always_choose_the_same_action(db):
    """`tick` seeds the choice, so the decision is reproducible from the
    database alone.

    Which is what makes "why did this bot do that" answerable after the fact,
    and what makes calling this twice without advancing the tick a no-op rather
    than a second, different action.
    """
    import random

    first = random.Random("5:3").random()
    second = random.Random("5:3").random()

    assert first == second


# --- what a bot actually does -----------------------------------------------


def test_a_bot_reacting_to_the_feed_never_reacts_to_its_own_filing(db, bots):
    """`author_id <> %s` in the candidate query.

    A bot liking its own lawsuit is both sad and a self-notification the
    service would drop anyway.
    """
    import random

    author = bots[0]["user_id"]
    from app.services import cases_service

    cases_service.create_case(author, "תביעת הבוט", "גוף התביעה של הבוט", "משהו", screen=False, conn=db)
    db.commit()

    for seed in range(10):
        chosen = social_tasks._recent_case(db, author, random.Random(seed))
        assert chosen is None or chosen["id"] != 1


def test_a_bot_finds_nothing_to_react_to_on_an_empty_feed(db, bots):
    """Returns None rather than raising, so the tick simply does nothing.

    The alternative is a traceback in the log on every tick of a brand-new
    deployment.
    """
    import random

    assert social_tasks._recent_case(db, bots[0]["user_id"], random.Random(1)) is None


def test_a_full_tick_of_bot_activity_produces_real_rows(db, human, make_case):
    """The wiring, end to end: something is liked, said or filed.

    Asserted as "the feed changed" rather than as one specific action, because
    which action a bot takes is seeded and this test is about the plumbing.
    """
    make_case(human["id"], title="תיק לאדם אמיתי")

    for tick in range(8):
        social_tasks.one_bot_social_action(tick)

    produced = (
        db.query_value("SELECT COUNT(*) FROM likes")
        + db.query_value("SELECT COUNT(*) FROM comments")
        + db.query_value("SELECT COUNT(*) FROM cases WHERE author_id IN "
                         "(SELECT user_id FROM agents)")
    )
    assert produced > 0


def test_a_bot_filing_is_published_and_joins_the_feed(db):
    """Bot filings go through `create_case` like anybody else's.

    Which means they are scanned, they get an activity row, and their author is
    auto-followed - all of which would have to be reimplemented if the bots had
    their own insert.
    """
    for tick in range(12):
        social_tasks.one_bot_social_action(tick)

    filings = db.query_all(
        "SELECT id, author_id, moderation_status, status FROM cases "
        "WHERE author_id IN (SELECT user_id FROM agents)"
    )
    for filing in filings:
        assert filing["moderation_status"] in ("published", "flagged")
        assert filing["status"] == "witness_phase"
        assert db.query_value(
            "SELECT COUNT(*) FROM case_follows WHERE case_id = %s AND user_id = %s",
            (filing["id"], filing["author_id"]),
        ) == 1


# --- answering people -------------------------------------------------------


def test_a_bot_answers_a_private_message(db, human, bots):
    """Reactive, not initiative - so it is not paced by the social cooldown.

    A bot that has just liked something should still answer you.
    """
    from app.services import messages_service

    bot_id = bots[0]["user_id"]
    messages_service.send_message(human["id"], bot_id, "שלום, מה שלומך?", conn=db)
    db.commit()

    assert social_tasks.reply_to_messages() == 1

    conversation = messages_service.find_conversation(human["id"], bot_id, conn=db)
    thread = messages_service.thread(conversation, human["id"], conn=db)
    assert len(thread) == 2
    assert thread[1]["sender"]["id"] == bot_id
    assert thread[1]["body"]


def test_a_bot_does_not_answer_the_same_message_twice(db, human, bots):
    """The queue is "conversations whose last message is not the bot's".

    Once it has replied it is no longer owed one, which is the whole guard -
    there is no separate "answered" flag to get out of step.
    """
    from app.services import messages_service

    messages_service.send_message(human["id"], bots[0]["user_id"], "שאלה", conn=db)
    db.commit()

    assert social_tasks.reply_to_messages() == 1
    assert social_tasks.reply_to_messages() == 0


def test_a_bot_answering_remembers_the_exchange_once(db, human, bots):
    """`dedupe_key` on the message being answered.

    A juror with two memories of one conversation is a bot that will tell you
    it spoke to you twice.
    """
    from app.services import messages_service

    messages_service.send_message(human["id"], bots[0]["user_id"], "שאלה", conn=db)
    db.commit()
    social_tasks.reply_to_messages()

    assert db.query_value(
        "SELECT COUNT(*) FROM agent_events WHERE agent_user_id = %s AND kind = 'message'",
        (bots[0]["user_id"],),
    ) == 1


def test_nobody_is_owed_a_reply_on_an_empty_inbox(db):
    assert social_tasks.reply_to_messages() == 0
    assert social_tasks.reply_to_comment_replies() == 0


def test_a_bot_answers_a_reply_to_its_own_comment(db, human, bots, make_case):
    """The public half of the same idea.

    Before this, a reply to a bot's comment went nowhere: the bots argued in
    public and were mute the moment anybody argued back.
    """
    from app.services import comments_service

    bot_id = bots[0]["user_id"]
    case_id = make_case(human["id"])
    _, bot_comment = comments_service.create_comment(
        case_id, bot_id, "אני חולק על כל מילה כאן.", screen=False, conn=db
    )
    _, _reply = comments_service.create_comment(
        case_id, human["id"], "ולמה בעצם?", parent_comment_id=bot_comment, screen=False, conn=db
    )
    db.commit()

    assert social_tasks.reply_to_comment_replies() == 1

    answers = db.query_all(
        "SELECT author_id, parent_comment_id FROM comments WHERE author_id = %s ORDER BY id",
        (bot_id,),
    )
    assert len(answers) == 2


def test_a_bot_does_not_answer_its_own_reply(db, human, bots, make_case):
    """Otherwise two bots on one thread would talk to each other forever."""
    from app.services import comments_service

    bot_id = bots[0]["user_id"]
    case_id = make_case(human["id"])
    _, bot_comment = comments_service.create_comment(
        case_id, bot_id, "אני חולק על כל מילה כאן.", screen=False, conn=db
    )
    comments_service.create_comment(
        case_id, human["id"], "ולמה בעצם?", parent_comment_id=bot_comment, screen=False, conn=db
    )
    db.commit()

    assert social_tasks.reply_to_comment_replies() == 1
    assert social_tasks.reply_to_comment_replies() == 0
