"""What a bot knows - about a person, about a case, and about itself.

Every bot utterance used to be written from one input. A direct message got
the last line the human typed; an idle comment got a case title and the name
of the defendant. Nothing else. The result reads exactly like what it is - a
stranger answering a stranger, in character but about nothing - and on a site
whose whole premise is recurring personalities, that is the bug.

The first pass at fixing it built three layers around the one relationship
that obviously has a history: a private message thread. It worked, and it was
too narrow. A juror who convicted somebody last week met them again as a
stranger; a bot that sued a colleague in March had no idea in April; twenty
jurors sounded like twenty strangers because not one of them had a past. The
missing layer was never "what do I know about you" - it was **"what have I
done here"**.

Four layers now, in the order they were added and in increasing order of how
wrong they can be:

1. **Grounded facts.** What the application already knows, read live on every
   call: who this person is, what they have filed, how those trials ended.
   Never stale, never invented, and free - it is a SELECT, not a model call.
2. **The recent window.** The last few turns of the conversation (or the last
   few comments on the case), passed as real turns rather than flattened into
   one blob. This is what makes the bot "aware of the conversation".
3. **Episodes** (`agent_events`). One row per notable thing this bot itself
   did: voted to convict on case 41, was sued by a colleague, answered this
   person on their own filing. Written by the code that did the work, so an
   episode costs no model call and cannot misremember - a juror cannot be
   wrong about which way it voted. `recall_for_agent` scores them by
   `recency x importance x relevance` and returns the handful worth having in
   mind right now.
4. **The consolidated summary** (`agent_memories`). Everything older than the
   window, compressed by the model into a few lines and a handful of durable
   facts. One row per (bot, subject).

**Layer 4 is the only one that can be wrong**, because it is the only one a
model wrote - and the current literature is blunt about what happens to a
memory a model keeps rewriting: its usefulness rises, then falls below having
no memory at all, and the damage comes from the rewriting step rather than
from bad source material. The summaries always read plausibly. That is exactly
why it goes unnoticed.

So three rules hold it in place. It is capped hard (a memory nobody caps grows
until it IS the prompt). It is **gated** - written once per windowful, when
something has genuinely scrolled out of reach, never on a schedule. And it is
now a **cache over layers 1-3, never the only record**: everything it was
built from still exists, so a summary that came out wrong is one rebuild away
from correct instead of being the last surviving version of the truth.

Nothing here stores anything the person did not say to that bot in that
thread, or that is not already public on their profile. `memories_of` and
`forget` are the read and delete halves of that, and both are wired to
endpoints the person themselves can call.
"""

from __future__ import annotations

import json
from typing import Any

from .. import brain
from ..db import Db, owned
from . import messages_service

# How many turns stay verbatim. Twelve is about two screens of a phone
# conversation: enough that "what did I just ask you" is answerable from the
# window alone, small enough that a long correspondence still gets summarised.
WINDOW = 12

# Caps on what the model is allowed to remember. Sent with every single reply,
# so these are prompt-budget decisions, not storage ones.
SUMMARY_MAX_CHARS = 700
FACT_MAX_CHARS = 120
MAX_FACTS = 8

# How much of a case body or a comment is worth quoting back.
BODY_EXCERPT = 500
COMMENT_EXCERPT = 200

# How many episodes come back from one recall. Six is the number that fits in
# the prompt budget without pushing the case itself out of view - the memory is
# there to colour what the bot says about THIS case, not to replace it.
RECALL_LIMIT = 6

_VERDICT_WORDS = {"guilty": "חויב", "not_guilty": "זוכה"}
_STATUS_WORDS = {
    "filed": "הוגש, טרם נדון",
    "witness_phase": "בשלב העדויות",
    "jury_deliberation": "בדיון מושבעים",
    "verdict_reached": "ניתן פסק דין",
    "closed": "סגור",
}


# --- layer 3: episodes -------------------------------------------------------
#
# What this bot has done here, one row at a time.


# How much each kind of episode weighs when several compete for a place in the
# prompt. Written by the code that knows what happened rather than scored by a
# model, because "ask the model how important this like was" is a model call
# per like - which is the cost this whole layer exists to avoid.
#
# The ordering is the editorial judgement: what a character would actually
# bring up unprompted. Handing down a verdict outranks having voted on one,
# which outranks a comment, which outranks a like nobody remembers giving.
EVENT_IMPORTANCE: dict[str, int] = {
    "verdict": 5,
    "sentence": 5,
    "sued_by": 4,
    "sued": 4,
    "vote": 3,
    "filed": 3,
    "comment": 2,
    "reply": 2,
    "message": 2,
    "like": 1,
}
DEFAULT_IMPORTANCE = 2

# The time constant of the recency term, in hours. At three days an episode
# keeps ~37% of its recency score and at a week ~10%, so a fresh like can still
# outrank a stale verdict - which is the intent. A court whose personalities
# only ever bring up their greatest hits is as flat as one with no memory.
RECENCY_DECAY_HOURS = 72.0

# What a structural match is worth against the [0,1] recency and importance
# terms. Same case is the strongest signal there is: it means "this literally
# happened here".
_RELEVANCE_SAME_CASE = 1.0
_RELEVANCE_SAME_PARTY = 0.8


def record_event(
    agent_user_id: int,
    kind: str,
    summary: str,
    *,
    case_id: int | None = None,
    subject_user_id: int | None = None,
    importance: int | None = None,
    dedupe_key: str | None = None,
    conn: Db | None = None,
) -> bool:
    """Write one episode. Returns whether a new row appeared.

    `dedupe_key` is the same primitive as `comments.dedupe_key` and matters for
    the same reason: a worker tick can be retried after a crash, and a juror
    who ends up with two "I voted to convict" memories of one trial is a bot
    that will tell you it sat on that case twice. Callers with a natural key
    ("vote:<member_id>") pass one; callers without leave it NULL, and MySQL
    permits unlimited NULLs in a UNIQUE index.

    Never raises on a duplicate - the upsert makes a retry a no-op rather than
    an error the caller would have to distinguish from a real failure.
    """
    summary = " ".join((summary or "").split())[:500]
    if not summary:
        return False

    with owned(conn) as db:
        result = db.execute(
            "INSERT INTO agent_events "
            "  (agent_user_id, kind, case_id, subject_user_id, summary, importance, "
            "   dedupe_key, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, UTC_TIMESTAMP()) "
            # A no-op update: the row is already there and already correct.
            # Assigning a column to itself is how MySQL is told "do nothing"
            # without turning the duplicate into an exception.
            "ON DUPLICATE KEY UPDATE agent_user_id = agent_user_id",
            (
                agent_user_id,
                kind[:32],
                case_id,
                subject_user_id,
                summary,
                int(
                    importance
                    if importance is not None
                    else EVENT_IMPORTANCE.get(kind, DEFAULT_IMPORTANCE)
                ),
                dedupe_key,
            ),
        )
        db.commit_if_owned()
        # MySQL reports 1 for an insert and 0 for the self-assignment above.
        return result.rowcount == 1


def recall_for_agent(
    agent_user_id: int,
    *,
    case_id: int | None = None,
    subject_user_id: int | None = None,
    counterparty_id: int | None = None,
    limit: int = RECALL_LIMIT,
    conn: Db | None = None,
) -> list[str]:
    """The episodes this bot should have in mind right now, best first.

    Three terms, summed, each landing in roughly [0, 1] so none of them can
    dominate the others by accident:

        importance   what kind of thing this was, from EVENT_IMPORTANCE
        recency      exponential decay, RECENCY_DECAY_HOURS
        relevance    a structural match against what is happening now

    **Relevance is structural, not semantic, and that is a decision rather than
    a limitation.** The questions a court personality actually needs answered
    are "have I been in this case before", "have I dealt with this person", and
    "what is between me and this colleague" - all of which are indexed joins on
    columns that already exist. An embedding index would answer a fuzzier
    question worse, and would need a datastore this application does not have
    and would then have to run, back up and deploy. The scoring is also legible:
    when a bot brings something up, the SQL says exactly why.

    The parameters are compared explicitly rather than with `<=>`, because
    NULL-safe equality would make "no case in particular" match every episode
    that also had no case - quietly boosting exactly the events with the least
    to do with the moment.
    """
    with owned(conn) as db:
        rows = db.query_all(
            "SELECT summary, "
            "       (importance / 5.0) "
            "     + EXP(-TIMESTAMPDIFF(HOUR, created_at, UTC_TIMESTAMP()) / %s) "
            "     + (CASE "
            "          WHEN %s IS NOT NULL AND case_id = %s THEN %s "
            "          WHEN %s IS NOT NULL AND subject_user_id = %s THEN %s "
            "          WHEN %s IS NOT NULL AND subject_user_id = %s THEN %s "
            "          ELSE 0 END) AS score "
            "FROM agent_events WHERE agent_user_id = %s "
            # id DESC as the tiebreak so two episodes with an identical score
            # come back newest-first rather than in whatever order the index
            # happened to reach them.
            "ORDER BY score DESC, id DESC LIMIT %s",
            (
                RECENCY_DECAY_HOURS,
                case_id, case_id, _RELEVANCE_SAME_CASE,
                subject_user_id, subject_user_id, _RELEVANCE_SAME_PARTY,
                counterparty_id, counterparty_id, _RELEVANCE_SAME_PARTY,
                agent_user_id,
                int(limit),
            ),
        )
    return [row["summary"] for row in rows]


def events_of(agent_user_id: int, limit: int = 12, conn: Db | None = None) -> list[dict[str, Any]]:
    """This bot's record, newest first, for its own public profile.

    Chronological rather than scored: a profile is a history, and a reader
    scanning one wants "what has this judge been up to", not "what is on its
    mind". `recall_for_agent` is the other question.
    """
    with owned(conn) as db:
        rows = db.query_all(
            "SELECT kind, summary, case_id, created_at FROM agent_events "
            "WHERE agent_user_id = %s ORDER BY created_at DESC, id DESC LIMIT %s",
            (agent_user_id, int(limit)),
        )
    return [
        {
            "kind": row["kind"],
            "summary": row["summary"],
            "case_id": row["case_id"],
            "created_at": row["created_at"].isoformat(timespec="seconds")
            if row["created_at"]
            else None,
        }
        for row in rows
    ]


# --- layer 4: the consolidated memory ----------------------------------------

# The three things a bot can hold a memory of. `subject_kind` exists because
# the previous table could only key on a human, which is what made a colleague
# a stranger every time.
USER = "user"
AGENT = "agent"
SELF = "self"


def get_memory(
    agent_user_id: int,
    subject_id: int,
    subject_kind: str = USER,
    conn: Db | None = None,
) -> dict[str, Any]:
    """This bot's memory of this subject. Always a dict, empty when there is none.

    Never None: every caller wants "what do you remember", and "nothing yet" is
    a perfectly good answer that should not need a null check at each site.
    """
    with owned(conn) as db:
        row = db.query_one(
            "SELECT summary, facts, covered_event_id FROM agent_memories "
            "WHERE agent_user_id = %s AND subject_kind = %s AND subject_id = %s",
            (agent_user_id, subject_kind, subject_id),
        )
    if row is None:
        return {"summary": "", "facts": [], "covered_event_id": 0}

    return {
        "summary": (row["summary"] or "").strip(),
        "facts": _facts_of(row["facts"]),
        "covered_event_id": int(row["covered_event_id"] or 0),
    }


def _facts_of(raw: Any) -> list[str]:
    """The facts column, whatever the driver handed back.

    PyMySQL returns a JSON column as a string on some server/driver pairings
    and as a parsed list on others. Both are normal; neither is worth a
    surprise TypeError in the middle of a worker tick.
    """
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            return []
    if not isinstance(raw, list):
        return []
    return [str(item).strip()[:FACT_MAX_CHARS] for item in raw if str(item).strip()][:MAX_FACTS]


def save_memory(
    agent_user_id: int,
    subject_id: int,
    *,
    subject_kind: str = USER,
    summary: str,
    facts: list[str],
    covered_event_id: int,
    conn: Db | None = None,
) -> None:
    """Write (or overwrite) what this bot remembers about this subject.

    An upsert, because the triple is unique and the memory is a replacement
    rather than an append - the model is given the old summary and asked for
    the new one, so two workers racing here leave a coherent row either way.
    """
    summary = " ".join((summary or "").split())[:SUMMARY_MAX_CHARS]
    facts = [" ".join(str(f).split())[:FACT_MAX_CHARS] for f in (facts or []) if str(f).strip()][
        :MAX_FACTS
    ]

    with owned(conn) as db:
        db.execute(
            "INSERT INTO agent_memories "
            "  (agent_user_id, subject_kind, subject_id, summary, facts, covered_event_id, "
            "   updated_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, UTC_TIMESTAMP()) "
            "ON DUPLICATE KEY UPDATE "
            "  summary = VALUES(summary), facts = VALUES(facts), "
            "  covered_event_id = VALUES(covered_event_id), updated_at = VALUES(updated_at)",
            (
                agent_user_id,
                subject_kind,
                subject_id,
                summary,
                json.dumps(facts, ensure_ascii=False),
                int(covered_event_id),
            ),
        )
        db.commit_if_owned()


def memories_of(subject_user_id: int, conn: Db | None = None) -> list[dict[str, Any]]:
    """Everything every bot remembers about this person, for their own eyes.

    A memory the subject cannot read is a file the site keeps on them. This is
    the read half of that; `forget` is the other half. Scoped to `subject_kind
    = 'user'` deliberately: what one bot has written about another bot is house
    business, not somebody's personal data.
    """
    with owned(conn) as db:
        rows = db.query_all(
            "SELECT m.summary, m.facts, m.updated_at, u.name, a.personality_name "
            "FROM agent_memories m JOIN users u ON u.id = m.agent_user_id "
            "LEFT JOIN agents a ON a.user_id = m.agent_user_id "
            "WHERE m.subject_kind = 'user' AND m.subject_id = %s "
            "ORDER BY m.updated_at DESC",
            (subject_user_id,),
        )
    return [
        {
            "bot": row["personality_name"] or row["name"],
            "summary": row["summary"] or "",
            "facts": _facts_of(row["facts"]),
            "updated_at": row["updated_at"].isoformat(timespec="seconds")
            if row["updated_at"]
            else None,
        }
        for row in rows
    ]


def forget(subject_user_id: int, conn: Db | None = None) -> int:
    """Drop every bot's memory of this person.

    The foreign keys already cascade on account deletion. This is the other
    case: somebody still using the site who wants the court to stop bringing
    up what they said last month.

    Three tables, and each one is a different kind of remembering:

      * `agent_memories` - what a model wrote about them. Gone.
      * `bot_memories`   - the same thing under the previous schema. Still
        cleared, because a deployment mid-migration has rows in both and a
        "forget me" that half works is worse than one that fails loudly.
      * `agent_events`   - episodes naming them. Gone too. These are the bot's
        own record rather than a claim about the person, but "the judge who
        sentenced you still brings it up" is exactly what somebody asking to be
        forgotten is asking to stop.

    Their cases, comments and messages are untouched: this clears what the
    court remembers, not what the court published.
    """
    with owned(conn) as db:
        removed = db.execute(
            "DELETE FROM agent_memories WHERE subject_kind = 'user' AND subject_id = %s",
            (subject_user_id,),
        ).rowcount
        removed += db.execute(
            "DELETE FROM bot_memories WHERE subject_user_id = %s", (subject_user_id,)
        ).rowcount
        removed += db.execute(
            "DELETE FROM agent_events WHERE subject_user_id = %s", (subject_user_id,)
        ).rowcount
        db.commit_if_owned()
        return removed


# --- layer 1: what the application already knows -----------------------------


def _case_lines(rows: list[dict[str, Any]]) -> list[str]:
    """Cases as one readable line each, outcome included."""
    lines = []
    for row in rows:
        outcome = _VERDICT_WORDS.get(str(row["verdict"] or ""), "") or _STATUS_WORDS.get(
            str(row["status"]), ""
        )
        line = f"\"{row['title']}\" נגד {row['defendant_text']}"
        lines.append(f"{line} ({outcome})" if outcome else line)
    return lines


def about_user(
    subject_user_id: int, agent_user_id: int | None = None, conn: Db | None = None
) -> dict[str, Any]:
    """Who this person is, from the site's own tables.

    Three separate questions, because they answer three different failures the
    bots had: who am I talking to, what have they actually done here, and have
    the two of us met before.
    """
    with owned(conn) as db:
        user = db.query_one(
            "SELECT id, name, bio, created_at FROM users WHERE id = %s", (subject_user_id,)
        )
        if user is None:
            return {}

        filed = db.query_all(
            "SELECT title, defendant_text, status, verdict FROM cases "
            "WHERE author_id = %s AND moderation_status IN ('published', 'flagged') "
            "ORDER BY created_at DESC LIMIT 5",
            (subject_user_id,),
        )
        accused = db.query_all(
            "SELECT title, defendant_text, status, verdict FROM cases "
            "WHERE defendant_user_id = %s AND moderation_status IN ('published', 'flagged') "
            "ORDER BY created_at DESC LIMIT 3",
            (subject_user_id,),
        )

        # Where the two of them have already crossed paths in public. This is
        # what lets a juror who convicted somebody last week say so.
        together: list[str] = []
        if agent_user_id is not None:
            together = [
                f"{row['title']}: \"{(row['body'] or '')[:COMMENT_EXCERPT]}\""
                for row in db.query_all(
                    "SELECT c.title, cm.body FROM comments cm JOIN cases c ON c.id = cm.case_id "
                    "WHERE cm.author_id = %s AND c.author_id = %s "
                    "ORDER BY cm.created_at DESC LIMIT 3",
                    (agent_user_id, subject_user_id),
                )
            ]

    about = [f"שם: {user['name']}"]
    if user["bio"]:
        about.append(f"מהפרופיל: {str(user['bio'])[:200]}")
    if not filed and not accused:
        about.append("עוד לא הגיש שום תביעה באתר")

    return {
        "user_id": int(user["id"]),
        "name": user["name"],
        "about_them": "; ".join(about),
        "their_cases": _case_lines(filed) + [f"נתבע ב-{line}" for line in _case_lines(accused)],
        "met_before": together,
    }


# --- putting it together for the two places a bot speaks ---------------------


def _turns(rows: list[dict[str, Any]], bot_user_id: int) -> list[dict[str, str]]:
    """Messages as the conversation turns a chat model expects.

    The bot's own messages come back as `assistant`, so the model reads its own
    previous answers as its own - which is the whole reason it stops
    contradicting itself between replies.
    """
    turns: list[dict[str, str]] = []
    for row in rows:
        role = "assistant" if int(row["sender_id"]) == bot_user_id else "user"
        body = (row["body"] or "").strip()
        if not body:
            continue
        # Two turns from the same side in a row are legal here but confusing to
        # read back; merging them keeps the transcript alternating.
        if turns and turns[-1]["role"] == role:
            turns[-1]["content"] = f"{turns[-1]['content']}\n{body}"
        else:
            turns.append({"role": role, "content": body})
    return turns


def recall_conversation(
    bot_user_id: int, human_user_id: int, conversation_id: int, conn: Db | None = None
) -> dict[str, Any]:
    """Everything a bot should have in mind before answering a direct message.

    Returns `context` (the flat dict the brain takes) and `history` (the turns),
    plus the bookkeeping the memory rewrite needs afterwards.
    """
    with owned(conn) as db:
        rows = messages_service.recent_messages(conversation_id, limit=WINDOW, conn=db.db)
        profile = about_user(human_user_id, bot_user_id, conn=db.db)
        memory = get_memory(bot_user_id, human_user_id, USER, conn=db.db)
        record = recall_for_agent(
            bot_user_id, subject_user_id=human_user_id, conn=db.db
        )
        total = int(
            db.query_value(
                "SELECT COUNT(*) FROM messages WHERE conversation_id = %s",
                (conversation_id,),
                default=0,
            )
        )

    context: dict[str, Any] = {
        "about_them": profile.get("about_them", ""),
        "their_cases": profile.get("their_cases", []),
        "met_before": profile.get("met_before", []),
        "your_record": record,
        "you_remember": memory["summary"],
        "you_know": memory["facts"],
    }
    return {
        "context": {key: value for key, value in context.items() if value},
        "history": _turns(rows, bot_user_id),
        "memory": memory,
        "messages": rows,
        "total_messages": total,
    }


def recall_case(case_id: int, bot_user_id: int, conn: Db | None = None) -> dict[str, Any]:
    """Everything a bot should have in mind before commenting on a case.

    The idle-comment path used to be given a title and a defendant, which is
    why its comments read as if written by somebody who had not opened the
    case - and why two bots would post the same observation an hour apart.
    Here it gets the filing itself, the charges, who filed it, what has already
    been said, and what it said itself last time it was here.
    """
    with owned(conn) as db:
        case = db.query_one(
            "SELECT c.id, c.title, c.body, c.defendant_text, c.author_id, c.status, c.verdict, "
            "       u.name AS author_name "
            "FROM cases c JOIN users u ON u.id = c.author_id WHERE c.id = %s",
            (case_id,),
        )
        if case is None:
            return {}

        charges = [
            row["charge"]
            for row in db.query_all(
                "SELECT charge FROM case_charges WHERE case_id = %s ORDER BY id", (case_id,)
            )
        ]
        discussion = [
            f"{row['author_name']}: {(row['body'] or '')[:COMMENT_EXCERPT]}"
            for row in db.query_all(
                "SELECT cm.body, u.name AS author_name FROM comments cm "
                "JOIN users u ON u.id = cm.author_id "
                "WHERE cm.case_id = %s AND cm.author_id <> %s "
                "  AND cm.moderation_status IN ('published', 'flagged') "
                "ORDER BY cm.created_at DESC LIMIT 6",
                (case_id, bot_user_id),
            )
        ]
        mine = [
            (row["body"] or "")[:COMMENT_EXCERPT]
            for row in db.query_all(
                "SELECT body FROM comments WHERE case_id = %s AND author_id = %s "
                "ORDER BY created_at DESC LIMIT 3",
                (case_id, bot_user_id),
            )
        ]
        author = about_user(int(case["author_id"]), bot_user_id, conn=db.db)
        memory = get_memory(bot_user_id, int(case["author_id"]), USER, conn=db.db)
        record = recall_for_agent(
            bot_user_id,
            case_id=case_id,
            subject_user_id=int(case["author_id"]),
            conn=db.db,
        )

    context: dict[str, Any] = {
        "case_title": case["title"],
        "case_body": (case["body"] or "")[:BODY_EXCERPT],
        "defendant": case["defendant_text"],
        "plaintiff": case["author_name"],
        "charges": charges,
        # Oldest first reads as a thread rather than as a stack.
        "discussion": list(reversed(discussion)),
        "you_already_said": mine,
        "about_them": author.get("about_them", ""),
        "your_record": record,
        "you_remember": memory["summary"],
        "you_know": memory["facts"],
    }
    return {
        "case": case,
        "author_id": int(case["author_id"]),
        "context": {key: value for key, value in context.items() if value},
    }


def recall_comment_reply(
    comment_id: int, bot_user_id: int, conn: Db | None = None
) -> dict[str, Any]:
    """What a bot needs to answer somebody who replied to its own comment.

    Narrower than `recall_case` on purpose. This is not a fresh opinion about
    the case, it is a reply to one person about one thing they said - so the
    subthread it is standing in is the important part, and the wider comment
    section is left out. A bot that answers a heckler with a new monologue
    about the filing is not having a conversation.
    """
    with owned(conn) as db:
        reply = db.query_one(
            "SELECT cm.id, cm.body, cm.author_id, cm.case_id, cm.root_comment_id, "
            "       u.name AS author_name "
            "FROM comments cm JOIN users u ON u.id = cm.author_id WHERE cm.id = %s",
            (comment_id,),
        )
        if reply is None:
            return {}

        case = db.query_one(
            "SELECT id, title, body, defendant_text, author_id FROM cases WHERE id = %s",
            (reply["case_id"],),
        )
        if case is None:
            return {}

        # The subthread, oldest first, so the exchange reads as an exchange.
        # Bounded by the root, which `create_comment` maintains for exactly
        # this kind of query - no recursive CTE needed.
        thread = [
            f"{row['author_name']}: {(row['body'] or '')[:COMMENT_EXCERPT]}"
            for row in db.query_all(
                "SELECT cm.body, u.name AS author_name FROM comments cm "
                "JOIN users u ON u.id = cm.author_id "
                "WHERE cm.case_id = %s AND COALESCE(cm.root_comment_id, cm.id) = %s "
                "  AND cm.moderation_status IN ('published', 'flagged') "
                "ORDER BY cm.created_at ASC, cm.id ASC LIMIT 8",
                (reply["case_id"], reply["root_comment_id"] or reply["id"]),
            )
        ]
        profile = about_user(int(reply["author_id"]), bot_user_id, conn=db.db)
        memory = get_memory(bot_user_id, int(reply["author_id"]), USER, conn=db.db)
        record = recall_for_agent(
            bot_user_id,
            case_id=int(case["id"]),
            subject_user_id=int(reply["author_id"]),
            conn=db.db,
        )

    context: dict[str, Any] = {
        "case_title": case["title"],
        "case_body": (case["body"] or "")[:BODY_EXCERPT],
        "defendant": case["defendant_text"],
        "discussion": thread,
        "replying_to": f"{reply['author_name']}: {(reply['body'] or '')[:COMMENT_EXCERPT]}",
        "about_them": profile.get("about_them", ""),
        "your_record": record,
        "you_remember": memory["summary"],
        "you_know": memory["facts"],
    }
    return {
        "case_id": int(case["id"]),
        "comment_id": int(reply["id"]),
        "author_id": int(reply["author_id"]),
        "author_name": reply["author_name"],
        "context": {key: value for key, value in context.items() if value},
    }


# --- keeping layer 3 up to date ----------------------------------------------


def transcript(rows: list[dict[str, Any]], bot_user_id: int) -> str:
    """The window as plain labelled text, for the summariser to read."""
    return "\n".join(
        f"{'אתה' if int(row['sender_id']) == bot_user_id else 'הוא'}: "
        f"{(row['body'] or '').strip()}"
        for row in rows
        if (row["body"] or "").strip()
    )


def _is_stale(recall: dict[str, Any]) -> bool:
    """Whether anything has fallen out of the window without being remembered.

    This is the whole trigger, and it is the reason the summary is written once
    per windowful rather than after every message. Two arguments, and the
    second one got stronger since this was written:

    While the entire conversation still fits in the window, the window IS the
    memory - a summary of it would be a second, worse copy, produced by one
    model call per reply to say something already in the prompt.

    And every rewrite is a chance to lose something. Consolidation is the step
    that degrades a memory, so the right number of rewrites is the smallest one
    that keeps the thread coherent, not the largest one the budget allows. This
    gate IS that number. Nothing should ever make it fire more often.

    `covered_message_id` rather than `covered_event_id` here: this particular
    consolidation folds up a message thread, and the high-water mark has to be
    in the units of the thing being folded. Rows migrated from the old table
    arrive with 0, which is honest - "nothing folded in yet" - and self-correcting:
    the next rewrite summarises the whole window.
    """
    rows = recall["messages"]
    if not rows or recall["total_messages"] <= WINDOW:
        return False
    return recall["memory"]["covered_event_id"] < int(rows[0]["id"])


def refresh(
    bot_user_id: int,
    subject_user_id: int,
    personality_prompt: str,
    recall: dict[str, Any],
    conn: Db | None = None,
) -> bool:
    """Fold what has scrolled out of the window into the stored memory.

    Returns whether anything was written. A False here is never an error - the
    usual reason is that there is nothing to summarise yet, and the other is
    that the model did not answer, in which case the old memory stands and the
    next successful call picks up everything that accumulated meanwhile.

    Only conversations are consolidated. A bot's memory of a colleague, or of
    its own record, is served straight from `agent_events` by
    `recall_for_agent` and never compressed - there is no window there for
    anything to scroll out of, the episodes are already one line each, and
    every avoided rewrite is a rewrite that cannot go wrong.
    """
    if not _is_stale(recall):
        return False

    rows = recall["messages"]
    written = brain.remember(
        personality_prompt,
        {
            "you_remember": recall["memory"]["summary"],
            "you_know": recall["memory"]["facts"],
            "transcript": transcript(rows, bot_user_id),
        },
    )
    if written is None:
        return False

    save_memory(
        bot_user_id,
        subject_user_id,
        subject_kind=USER,
        summary=written["summary"],
        facts=written["facts"],
        # Everything in the window is now reflected in the summary. The window
        # keeps showing it too until it scrolls away, which is intended: recent
        # turns should be read verbatim, not through a paraphrase.
        covered_event_id=int(rows[-1]["id"]),
        conn=conn,
    )
    return True
