"""Direct messages - one conversation per pair, guaranteed.

The pair's ids are **sorted before every lookup and insert**, so (a,b) and
(b,a) resolve to the same row and the UNIQUE index on (user_a_id, user_b_id)
does the rest. Two people messaging each other simultaneously for the first
time cannot create two conversations: one INSERT wins and the other is
absorbed.

That ordering would ideally also be a CHECK constraint, but MySQL rejects a
CHECK over a column written by a foreign key's ON DELETE CASCADE, and the
cascade is worth more here. `_ordered()` is the single place the rule lives.
"""

from __future__ import annotations

from typing import Any

import pymysql

from ..db import Db, owned
from . import notifications_service

BODY_MAX_LENGTH = 2000


def _ordered(a: int, b: int) -> tuple[int, int]:
    """The canonical (low, high) form of a pair."""
    return (a, b) if a < b else (b, a)


def conversation_for_pair(user_a: int, user_b: int, conn: Db | None = None) -> int | None:
    """Find or create the one conversation these two share."""
    if user_a == user_b:
        return None

    low, high = _ordered(user_a, user_b)
    with owned(conn) as db:
        existing = db.query_one(
            "SELECT id FROM conversations WHERE user_a_id = %s AND user_b_id = %s", (low, high)
        )
        if existing:
            return int(existing["id"])

        try:
            result = db.execute(
                "INSERT INTO conversations (user_a_id, user_b_id, created_at) "
                "VALUES (%s, %s, UTC_TIMESTAMP())",
                (low, high),
            )
        except pymysql.err.IntegrityError:
            # Someone created it between our SELECT and INSERT. Theirs is fine.
            row = db.query_one(
                "SELECT id FROM conversations WHERE user_a_id = %s AND user_b_id = %s", (low, high)
            )
            return int(row["id"]) if row else None

        db.commit_if_owned()
        return int(result.lastrowid)


def send_message(
    sender_id: int, recipient_id: int, body: str, conn: Db | None = None
) -> tuple[str, int | None]:
    body = (body or "").strip()[:BODY_MAX_LENGTH]
    if not body:
        return "invalid", None
    if sender_id == recipient_id:
        return "invalid", None

    with owned(conn) as db:
        recipient = db.query_one(
            "SELECT id, name, status, is_bot FROM users WHERE id = %s", (recipient_id,)
        )
        if recipient is None or recipient["status"] != "active":
            return "not_found", None

        conversation_id = conversation_for_pair(sender_id, recipient_id, conn=db.db)
        if conversation_id is None:
            return "invalid", None

        result = db.execute(
            "INSERT INTO messages (conversation_id, sender_id, body, created_at) "
            "VALUES (%s, %s, %s, UTC_TIMESTAMP())",
            (conversation_id, sender_id, body),
        )
        db.execute(
            "UPDATE conversations SET last_message_at = UTC_TIMESTAMP() WHERE id = %s",
            (conversation_id,),
        )
        notifications_service.notify(
            recipient_id,
            "message",
            actor_user_id=sender_id,
            payload={"conversation_id": conversation_id, "excerpt": body[:120]},
            conn=db.db,
        )
        db.commit_if_owned()
        return "ok", result.lastrowid


def list_conversations(user_id: int, conn: Db | None = None) -> list[dict[str, Any]]:
    """Every conversation this user is in, most recent first, with the other
    person and the unread count."""
    with owned(conn) as db:
        rows = db.query_all(
            "SELECT c.id, c.last_message_at, "
            "       CASE WHEN c.user_a_id = %s THEN c.user_b_id ELSE c.user_a_id END AS other_id "
            "FROM conversations c "
            "WHERE c.user_a_id = %s OR c.user_b_id = %s "
            "ORDER BY COALESCE(c.last_message_at, c.created_at) DESC",
            (user_id, user_id, user_id),
        )
        conversations = []
        for row in rows:
            other = db.query_one(
                "SELECT id, name, avatar_url, is_bot FROM users WHERE id = %s", (row["other_id"],)
            )
            last = db.query_one(
                "SELECT body, sender_id, created_at FROM messages "
                "WHERE conversation_id = %s ORDER BY id DESC LIMIT 1",
                (row["id"],),
            )
            unread = int(
                db.query_value(
                    "SELECT COUNT(*) FROM messages "
                    "WHERE conversation_id = %s AND sender_id <> %s AND read_at IS NULL",
                    (row["id"], user_id),
                    default=0,
                )
            )
            conversations.append(
                {
                    "id": row["id"],
                    "other": {
                        "id": other["id"],
                        "name": other["name"],
                        "avatar_url": other["avatar_url"],
                        "is_bot": bool(other["is_bot"]),
                    }
                    if other
                    else None,
                    "last_message": (
                        {
                            "body": last["body"][:120],
                            "sender_id": last["sender_id"],
                            "created_at": last["created_at"].isoformat(timespec="seconds"),
                        }
                        if last
                        else None
                    ),
                    "unread_count": unread,
                }
            )
        return conversations


def is_participant(conversation_id: int, user_id: int, conn: Db | None = None) -> bool:
    with owned(conn) as db:
        return (
            db.query_one(
                "SELECT 1 AS hit FROM conversations "
                "WHERE id = %s AND (user_a_id = %s OR user_b_id = %s)",
                (conversation_id, user_id, user_id),
            )
            is not None
        )


def thread(
    conversation_id: int, user_id: int, *, limit: int = 100, conn: Db | None = None
) -> list[dict[str, Any]] | None:
    """The messages, oldest first. None if the viewer is not in it."""
    with owned(conn) as db:
        if not is_participant(conversation_id, user_id, conn=db.db):
            return None

        rows = db.query_all(
            "SELECT m.*, u.name AS sender_name FROM messages m "
            "JOIN users u ON u.id = m.sender_id "
            "WHERE m.conversation_id = %s ORDER BY m.id ASC LIMIT %s",
            (conversation_id, int(limit)),
        )
    return [
        {
            "id": row["id"],
            "conversation_id": row["conversation_id"],
            "sender": {"id": row["sender_id"], "name": row["sender_name"]},
            "body": row["body"],
            "read_at": row["read_at"].isoformat(timespec="seconds") if row["read_at"] else None,
            "created_at": row["created_at"].isoformat(timespec="seconds"),
            "is_mine": row["sender_id"] == user_id,
        }
        for row in rows
    ]


def mark_thread_read(conversation_id: int, user_id: int, conn: Db | None = None) -> int:
    """Mark the OTHER person's messages read. Never your own."""
    with owned(conn) as db:
        if not is_participant(conversation_id, user_id, conn=db.db):
            return 0
        result = db.execute(
            "UPDATE messages SET read_at = UTC_TIMESTAMP() "
            "WHERE conversation_id = %s AND sender_id <> %s AND read_at IS NULL",
            (conversation_id, user_id),
        )
        db.commit_if_owned()
        return result.rowcount


def unread_total(user_id: int, conn: Db | None = None) -> int:
    with owned(conn) as db:
        return int(
            db.query_value(
                "SELECT COUNT(*) FROM messages m JOIN conversations c ON c.id = m.conversation_id "
                "WHERE (c.user_a_id = %s OR c.user_b_id = %s) "
                "  AND m.sender_id <> %s AND m.read_at IS NULL",
                (user_id, user_id, user_id),
                default=0,
            )
        )
