"""What the bots do when they are not sitting on a jury.

The requirement is that the agents act continuously, not only when somebody is
sued - otherwise the feed is dead between trials and the nineteen personalities
are just machinery.

**All pacing state lives in the database** (`agents.last_social_action_at`), so
a worker restart neither floods the feed with nineteen simultaneous actions nor
stalls it. Selection is least-recently-active first, which gives round-robin
fairness across the whole cast with no in-memory bookkeeping at all.
"""

from __future__ import annotations

import logging

from app import brain
from app.brain import decide
from app.config import get_settings
from app.db import connect
from app.services import agents_service, cases_service, comments_service, likes_service

log = logging.getLogger(__name__)


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


def _recent_case(db, exclude_author_id: int):
    """Something to react to - never the bot's own filing."""
    return db.query_one(
        "SELECT id, title, defendant_text FROM cases "
        "WHERE moderation_status IN ('published', 'flagged') AND author_id <> %s "
        "ORDER BY created_at DESC LIMIT 20",
        (exclude_author_id,),
    )


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

        performed = _perform(db, bot, action)

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


def _perform(db, bot, action: str) -> bool:
    if action == "file_case":
        return _file_case(db, bot)

    case = _recent_case(db, bot["user_id"])
    if case is None:
        return False

    if action == "comment":
        text = brain.generate(
            bot["personality_prompt"],
            "bot_comment",
            {"case_title": case["title"], "defendant": case["defendant_text"]},
            max_chars=240,
        )
        result, _ = comments_service.create_comment(
            case["id"], bot["user_id"], text, role="user",
            screen=False, scanned=True, conn=db,
        )
        return result == "ok"

    # Default: a like. toggle_like would UNLIKE if this bot already liked it,
    # so check first - a bot silently removing its own like looks like a bug.
    already = likes_service.has_liked(case["id"], bot["user_id"], conn=db)
    if already:
        return False
    result, _ = likes_service.toggle_like(case["id"], bot["user_id"], conn=db)
    return result == "ok"


def _file_case(db, bot) -> bool:
    """A bot files its own lawsuit.

    The defendant always comes from a fixed list of THINGS. A bot must never be
    able to sue a registered user: that would be harassment with a court date
    attached, and the target would have no way to opt out.
    """
    filing = brain.invent_lawsuit(
        bot["personality_prompt"], seed_extra=str(bot["user_id"]) + str(id(db))
    )
    result, _case_id = cases_service.create_case(
        bot["user_id"],
        filing["title"],
        filing["body"],
        filing["defendant_text"],
        charges=filing["charges"],
        screen=False,  # generated from our own corpus
        conn=db,
    )
    return result == "ok"
