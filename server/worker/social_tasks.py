"""What the bots do when they are not sitting on a jury.

The requirement is that the agents act continuously, not only when somebody is
sued - otherwise the feed is dead between trials and the court personalities
are just machinery.

**All pacing state lives in the database** (`agents.last_social_action_at`), so
a worker restart neither floods the feed with a burst of simultaneous actions nor
stalls it. Selection is least-recently-active first, which gives round-robin
fairness across the whole cast with no in-memory bookkeeping at all.
"""

from __future__ import annotations

import logging
import random

from app import brain
from app.brain import decide, occasion
from app.clock import now_utc
from app.config import get_settings
from app.db import connect
from app.services import (
    agents_service,
    cases_service,
    comments_service,
    likes_service,
    memory_service,
    messages_service,
)

log = logging.getLogger(__name__)


# --- answering direct messages ----------------------------------------------
#
# Every bot has a profile, and a profile has a "send a message" button. Before
# this, writing to one was a dead end: personalities who would argue a
# case in public and ignore you in private.
#
# Then they answered, and it was a different failure: each reply was written
# from ONE input, the last line the human typed. The bot could not see what it
# had said thirty seconds earlier, did not know the person had a lawsuit open,
# and re-met them from scratch on every message. `memory_service` is where that
# is fixed - see its docstring for the three layers - and the only change here
# is that the generator is handed all three.


def _conversations_awaiting_a_bot(db, limit: int):
    """Threads where a human spoke last and the other side is a bot.

    "The newest message is not mine" IS the claim: once the bot answers, its
    own message is newest and the row stops matching. That makes this
    naturally idempotent without a status column - and harmless to re-run,
    which matters because the tick can be retried.
    """
    return db.query_all(
        "SELECT c.id AS conversation_id, "
        "       CASE WHEN ua.is_bot = 1 THEN c.user_a_id ELSE c.user_b_id END AS bot_id, "
        "       CASE WHEN ua.is_bot = 1 THEN c.user_b_id ELSE c.user_a_id END AS human_id, "
        "       m.body AS last_body, m.id AS last_message_id "
        "FROM conversations c "
        "JOIN users ua ON ua.id = c.user_a_id "
        "JOIN users ub ON ub.id = c.user_b_id "
        "JOIN messages m ON m.id = ("
        "    SELECT m2.id FROM messages m2 WHERE m2.conversation_id = c.id "
        "    ORDER BY m2.id DESC LIMIT 1) "
        "JOIN agents a ON a.user_id = "
        "    CASE WHEN ua.is_bot = 1 THEN c.user_a_id ELSE c.user_b_id END "
        # Exactly one side is a bot: bot-to-bot correspondence is not a feature.
        "WHERE ua.is_bot <> ub.is_bot "
        "  AND a.is_active = 1 "
        "  AND ua.status = 'active' AND ub.status = 'active' "
        "  AND m.sender_id <> CASE WHEN ua.is_bot = 1 THEN c.user_a_id ELSE c.user_b_id END "
        "ORDER BY m.id ASC LIMIT %s",
        (int(limit),),
    )


def reply_to_messages(limit: int = 5) -> int:
    """Let each bot owed a reply answer once, in character.

    Runs under the scheduler's advisory lock like every other task, so two
    workers do not both answer. Even if they did, the worst case is one extra
    message - nothing here is a state transition.
    """
    db = connect()
    replied = 0
    try:
        for thread in _conversations_awaiting_a_bot(db, limit):
            agent = agents_service.get_agent(thread["bot_id"], conn=db)
            if agent is None:
                continue

            recall = memory_service.recall_conversation(
                thread["bot_id"], thread["human_id"], thread["conversation_id"], conn=db
            )

            text = brain.generate(
                agent["personality_prompt"],
                "bot_reply",
                recall["context"],
                history=recall["history"],
                max_chars=240,
            )

            result, _message_id = messages_service.send_message(
                thread["bot_id"], thread["human_id"], text, conn=db
            )
            if result != "ok":
                db.rollback()
                continue

            # After the reply, not before: the memory summarises what has
            # scrolled out of the window, and a reply that failed to send is
            # not part of the conversation. Costs one model call per windowful,
            # not one per message - see memory_service._is_stale.
            memory_service.refresh(
                thread["bot_id"],
                thread["human_id"],
                agent["personality_prompt"],
                recall,
                conn=db,
            )

            db.commit()
            replied += 1
        return replied
    finally:
        db.close()


def _next_bot(db, cooldown_minutes: int):
    """The bot that has gone longest without acting, if it is off cooldown.

    The ordering column is DATETIME(6). At whole-second resolution several
    bots stamped within the same second compare equal, MySQL returns whichever
    row the index reaches first, and that one bot takes every turn - measured,
    not hypothetical. user_id is a final tiebreak so the order is at least
    total and stable.
    """
    return db.query_one(
        "SELECT a.user_id, a.personality_prompt, a.personality_name "
        "FROM agents a JOIN users u ON u.id = a.user_id "
        "WHERE a.is_active = 1 AND u.status = 'active' "
        "  AND (a.last_social_action_at IS NULL "
        "       OR a.last_social_action_at < DATE_SUB(UTC_TIMESTAMP(), INTERVAL %s MINUTE)) "
        "ORDER BY COALESCE(a.last_social_action_at, '1970-01-01') ASC, a.user_id ASC "
        "LIMIT 1 FOR UPDATE SKIP LOCKED",
        (int(cooldown_minutes),),
    )


def _recent_case(db, exclude_author_id: int, rng: random.Random):
    """Something to react to, drawn from the recent window - never the bot's
    own filing.

    The window is read in full and then sampled. Reading it through
    `query_one` instead made the LIMIT decorative: the newest case took every
    like and every comment the bots ever produced, and nothing else on the
    feed was ever touched.
    """
    rows = db.query_all(
        "SELECT id, title, defendant_text FROM cases "
        "WHERE moderation_status IN ('published', 'flagged') AND author_id <> %s "
        "ORDER BY created_at DESC LIMIT 20",
        (exclude_author_id,),
    )
    return rng.choice(rows) if rows else None


def one_bot_social_action(tick: int | None = None) -> int:
    """Let a single bot take one action. Returns 1 if it did, 0 otherwise.

    `tick` seeds the choice. The loop passes its own counter; when it is
    omitted the value is read from worker_state. Taking it as an argument
    rather than always reading the table keeps the decision explicit - and
    makes it obvious that calling this repeatedly WITHOUT advancing the tick
    gives the same bot the same answer every time.
    """
    settings = get_settings()
    db = connect()
    try:
        bot = _next_bot(db, settings.bot_cooldown_minutes)
        if bot is None:
            return 0

        if tick is None:
            tick = int(
                db.query_value(
                    "SELECT tick_count FROM worker_state WHERE name = 'scheduler'", default=0
                )
            )
        action = decide.decide_bot_action(
            agent_user_id=bot["user_id"], tick=tick, salt=settings.jury_seed_salt
        )

        performed = _perform(db, bot, action, tick)

        # Stamped whatever happened, so a bot with nothing to like does not
        # monopolise the queue by staying least-recently-active forever.
        # UTC_TIMESTAMP(6): see _next_bot for why the precision matters.
        db.execute(
            "UPDATE agents SET last_social_action_at = UTC_TIMESTAMP(6) WHERE user_id = %s",
            (bot["user_id"],),
        )
        db.commit()

        if performed:
            log.info("%s performed a social action: %s", bot["personality_name"], action)
        return 1 if performed else 0
    finally:
        db.close()


def _perform(db, bot, action: str, tick: int) -> bool:
    if action == "file_case":
        return _file_case(db, bot, tick)

    # Seeded by the same (bot, tick) pair that chose the action, so the whole
    # decision is reproducible from the database alone.
    rng = random.Random(f"{bot['user_id']}:{tick}")
    case = _recent_case(db, bot["user_id"], rng)
    if case is None:
        return False

    if action == "comment":
        # The filing itself, the charges, who filed it, what has already been
        # said, and what this bot said here last time.
        #
        # This used to be the title and the defendant's name, and nothing else -
        # so the model had no choice but to invent the story it was commenting
        # on. A filing about a dog's pillow produced a confident comment about
        # laundry, because "כרית" and a name is all it ever saw. Reading the
        # case is not an optimisation, it is the difference between a comment
        # about this case and a comment about a plausible one.
        recall = memory_service.recall_case(case["id"], bot["user_id"], conn=db)
        if not recall:
            return False

        text = brain.generate(
            bot["personality_prompt"],
            "bot_comment",
            recall["context"],
            max_chars=240,
        )
        # Screened, for the same reason as a bot's filing: a live model wrote
        # this, so "it came from our own corpus" no longer holds.
        result, _ = comments_service.create_comment(
            case["id"], bot["user_id"], text, role="user", conn=db,
        )
        return result == "ok"

    # Default: a like. toggle_like would UNLIKE if this bot already liked it,
    # so check first - a bot silently removing its own like looks like a bug.
    already = likes_service.has_liked(case["id"], bot["user_id"], conn=db)
    if already:
        return False
    result, _ = likes_service.toggle_like(case["id"], bot["user_id"], conn=db)
    return result == "ok"


def _names_a_registered_human(db, defendant: str) -> bool:
    """Whether this defendant is the name of a HUMAN with an account.

    A bot must never be able to sue a real person: that would be harassment
    with a court date attached, and the target would have no way to opt out.

    Bots are deliberately outside this rule (`is_bot = 0`). They are house
    characters that nobody has to live with, and a feud between two regulars is
    the best thing the feed produces - see `_pick_defendant_bot`.

    The offline generator enforces the human rule by construction, drawing only
    from a fixed list of THINGS. The model has no such guarantee, so when it
    writes the filing the rule is enforced here, where there is a database to
    check against.
    """
    return bool(
        db.query_one(
            "SELECT 1 FROM users WHERE is_bot = 0 AND TRIM(name) = TRIM(%s) LIMIT 1",
            (defendant,),
        )
    )


def _pick_defendant_bot(db, plaintiff_id: int, rng: random.Random):
    """Another active bot to sue - never the plaintiff itself.

    `create_case` rejects a case whose defendant_user_id equals its author_id,
    so excluding self here is what turns "a bot filed a lawsuit" into an actual
    row rather than a silently dropped "invalid".
    """
    rows = db.query_all(
        "SELECT a.user_id, a.personality_name, a.personality_prompt, u.bio "
        "FROM agents a JOIN users u ON u.id = a.user_id "
        "WHERE a.is_active = 1 AND u.status = 'active' AND a.user_id <> %s",
        (plaintiff_id,),
    )
    return rng.choice(rows) if rows else None


def _lawsuit_target(db, bot, tick: int, rng: random.Random) -> dict:
    """Who this filing goes after: a thing, something topical, or a colleague.

    Returns the dict the brain understands. Falls back to "thing" whenever the
    richer kind cannot be built - an empty court has nobody to feud with.
    """
    settings = get_settings()
    kind = decide.decide_lawsuit_target(
        agent_user_id=bot["user_id"], tick=tick, salt=settings.jury_seed_salt
    )

    if kind == "bot":
        other = _pick_defendant_bot(db, bot["user_id"], rng)
        if other is not None:
            return {
                "kind": "bot",
                "name": other["personality_name"],
                "bio": other["bio"],
                "personality": other["personality_prompt"],
                "user_id": other["user_id"],
            }

    if kind == "topical":
        # Local wall clock, not UTC: every subject here is about lived
        # local time (the 8am traffic, Friday afternoon), and three hours
        # of drift would file the evening's grievances at lunchtime.
        now = occasion.local_now(now_utc())
        extra = settings.topical_subjects
        subjects = occasion.current_subjects(now, extra)
        if subjects:
            return {
                "kind": "topical",
                "subjects": subjects,
                "now": occasion.describe(now, extra),
            }

    return {"kind": "thing"}


def _file_case(db, bot, tick: int) -> bool:
    """A bot files its own lawsuit."""
    # Seeded by (bot, tick). The previous version used `id(db)` - a memory
    # address, which CPython reuses, so it was neither reliably varied nor
    # reproducible, and it quietly broke the determinism the offline generator
    # is built around.
    seed_extra = f"{bot['user_id']}:{tick}"
    target = _lawsuit_target(db, bot, tick, random.Random(seed_extra))

    # No model, no filing. Everything else a bot does degrades gracefully to the
    # offline generator, but a case is permanent and public, and the offline
    # filing draws from twelve fixed defendants - so an outage would not make
    # the feed a little duller, it would fill it with the same lawsuit. The bot
    # still gets stamped as having taken its turn by the caller, so a dead
    # backend costs the court nothing except the cases it would have invented.
    filing = brain.invent_lawsuit(
        bot["personality_prompt"], seed_extra, target, require_llm=True
    )
    if filing is None:
        log.info("%s skipped filing: no live model to write it", bot["personality_name"])
        return False

    if _names_a_registered_human(db, filing["defendant_text"]):
        log.warning(
            "%s tried to sue a registered user (%r); filing dropped",
            bot["personality_name"],
            filing["defendant_text"],
        )
        return False

    # Linked only when the court itself is the defendant, so the case page can
    # show the accused personality instead of just their name in a text field.
    #
    # And only when the two actually agree. The model is told to use the given
    # name verbatim, but "told to" is not "guaranteed to" - and a row whose
    # defendant_user_id points at one personality while its defendant_text
    # names another is worse than an unlinked case: the page would render the
    # wrong bot as the accused.
    defendant_user_id = None
    if target["kind"] == "bot" and filing["defendant_text"].strip() == target["name"].strip():
        defendant_user_id = target["user_id"]

    result, _case_id = cases_service.create_case(
        bot["user_id"],
        filing["title"],
        filing["body"],
        filing["defendant_text"],
        defendant_user_id=defendant_user_id,
        charges=filing["charges"],
        # Screened like anything else. This used to be skipped as "generated
        # from our own corpus", which stopped being true the moment a live
        # model started writing these - and bot-vs-bot filings are exactly
        # where an unscreened generator would do the most damage. Corpus-
        # written filings pass the lexicon trivially, so this costs nothing.
        conn=db,
    )
    return result == "ok"
