"""What a bot knows about a person and about a case, before it opens its mouth.

Every bot utterance used to be written from one input. A direct message got
the last line the human typed; an idle comment got a case title and the name
of the defendant. Nothing else. The result reads exactly like what it is - a
stranger answering a stranger, in character but about nothing - and on a site
whose whole premise is recurring personalities, that is the bug.

The fix is the standard three-layer memory, and only the third layer is new
storage:

1. **Grounded facts.** What the application already knows, read live on every
   call: who this person is, what they have filed, how those trials ended, and
   what this particular bot has already said to them or about them. Never
   stale, never invented, and free - it is a SELECT, not a model call.
2. **The recent window.** The last few turns of the conversation (or the last
   few comments on the case), passed as real turns rather than flattened into
   one blob. This is what makes the bot "aware of the conversation".
3. **The rolling summary** (`bot_memories`). Everything older than the window,
   compressed by the model into a few lines and a handful of durable facts,
   rewritten as the thread grows. One row per (bot, person) pair.

**Layer 3 is the only one that can be wrong**, because it is the only one a
model wrote. It is therefore capped hard (a memory nobody caps grows until it
IS the prompt), never written by the offline generator - a made-up "fact"
about a real user is worse than no memory at all - and deleted by the database
itself when either party is deleted, which is the only honest answer to
"forget me".

Nothing here stores anything the person did not say to that bot in that
thread, or that is not already public on their profile.
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

_VERDICT_WORDS = {"guilty": "חויב", "not_guilty": "זוכה"}
_STATUS_WORDS = {
    "filed": "הוגש, טרם נדון",
    "witness_phase": "בשלב העדויות",
    "jury_deliberation": "בדיון מושבעים",
    "verdict_reached": "ניתן פסק דין",
    "closed": "סגור",
}


# --- layer 3: the stored memory ---------------------------------------------


def get_memory(agent_user_id: int, subject_user_id: int, conn: Db | None = None) -> dict[str, Any]:
    """This bot's memory of this person. Always a dict, empty when there is none.

    Never None: every caller wants "what do you remember", and "nothing yet" is
    a perfectly good answer that should not need a null check at each site.
    """
    with owned(conn) as db:
        row = db.query_one(
            "SELECT summary, facts, covered_message_id FROM bot_memories "
            "WHERE agent_user_id = %s AND subject_user_id = %s",
            (agent_user_id, subject_user_id),
        )
    if row is None:
        return {"summary": "", "facts": [], "covered_message_id": 0}

    return {
        "summary": (row["summary"] or "").strip(),
        "facts": _facts_of(row["facts"]),
        "covered_message_id": int(row["covered_message_id"] or 0),
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
    subject_user_id: int,
    *,
    summary: str,
    facts: list[str],
    covered_message_id: int,
    conn: Db | None = None,
) -> None:
    """Write (or overwrite) what this bot remembers about this person.

    An upsert, because the pair is unique and the memory is a replacement
    rather than an append - the model is given the old summary and asked for
    the new one, so two workers racing here leave a coherent row either way.
    """
    summary = " ".join((summary or "").split())[:SUMMARY_MAX_CHARS]
    facts = [" ".join(str(f).split())[:FACT_MAX_CHARS] for f in (facts or []) if str(f).strip()][
        :MAX_FACTS
    ]

    with owned(conn) as db:
        db.execute(
            "INSERT INTO bot_memories "
            "  (agent_user_id, subject_user_id, summary, facts, covered_message_id, updated_at) "
            "VALUES (%s, %s, %s, %s, %s, UTC_TIMESTAMP()) "
            "ON DUPLICATE KEY UPDATE "
            "  summary = VALUES(summary), facts = VALUES(facts), "
            "  covered_message_id = VALUES(covered_message_id), updated_at = VALUES(updated_at)",
            (
                agent_user_id,
                subject_user_id,
                summary,
                json.dumps(facts, ensure_ascii=False),
                int(covered_message_id),
            ),
        )
        db.commit_if_owned()


def memories_of(subject_user_id: int, conn: Db | None = None) -> list[dict[str, Any]]:
    """Everything every bot remembers about this person, for their own eyes.

    A memory the subject cannot read is a file the site keeps on them. This is
    the read half of that; `forget` is the other half.
    """
    with owned(conn) as db:
        rows = db.query_all(
            "SELECT m.summary, m.facts, m.updated_at, u.name, a.personality_name "
            "FROM bot_memories m JOIN users u ON u.id = m.agent_user_id "
            "LEFT JOIN agents a ON a.user_id = m.agent_user_id "
            "WHERE m.subject_user_id = %s ORDER BY m.updated_at DESC",
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
    """
    with owned(conn) as db:
        result = db.execute(
            "DELETE FROM bot_memories WHERE subject_user_id = %s", (subject_user_id,)
        )
        db.commit_if_owned()
        return result.rowcount


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
        memory = get_memory(bot_user_id, human_user_id, conn=db.db)
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
        memory = get_memory(bot_user_id, int(case["author_id"]), conn=db.db)

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
        "you_remember": memory["summary"],
        "you_know": memory["facts"],
    }
    return {
        "case": case,
        "author_id": int(case["author_id"]),
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

    This is the whole trigger, and it is why the summary is written once per
    windowful rather than after every message: while the entire conversation
    still fits in the window, the window IS the memory and a summary of it
    would be a second, worse copy - one model call per reply, to say something
    already in the prompt.
    """
    rows = recall["messages"]
    if not rows or recall["total_messages"] <= WINDOW:
        return False
    return recall["memory"]["covered_message_id"] < int(rows[0]["id"])


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
        summary=written["summary"],
        facts=written["facts"],
        # Everything in the window is now reflected in the summary. The window
        # keeps showing it too until it scrolls away, which is intended: recent
        # turns should be read verbatim, not through a paraphrase.
        covered_message_id=int(rows[-1]["id"]),
        conn=conn,
    )
    return True
