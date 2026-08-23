"""Notifications - and, incidentally, the real-time bus.

The worker runs in its own container and creates most notifications; the SSE
endpoint that delivers them runs in the web process. The two share nothing but
this database, so rather than introduce a message broker the stream is simply a
cursor over the monotonically increasing `notifications.id` (see the
`idx_notif_stream(user_id, id)` index).

That means a notification written by any process, at any time, reaches every
connected browser with no coordination whatsoever - and nothing is lost across
a restart, because the cursor is a durable row id.
"""

from __future__ import annotations

import json
from typing import Any

from ..db import Db, owned

# Kept in step with the `type` enum in database/init.sql.
TYPES = (
    "summons",
    "verdict",
    "like",
    "comment",
    "message",
    "moderation",
    "testimony",
)


def shape_notification(row: dict[str, Any]) -> dict[str, Any]:
    """Row -> API JSON. Pure; mirrored by types.ts."""
    payload = row.get("payload")
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except ValueError:  # pragma: no cover - only if a row is hand-edited
            payload = None
    created = row.get("created_at")
    return {
        "id": row["id"],
        "type": row["type"],
        "case_id": row.get("case_id"),
        "actor": (
            {"id": row["actor_user_id"], "name": row.get("actor_name")}
            if row.get("actor_user_id")
            else None
        ),
        "payload": payload or {},
        "is_read": bool(row["is_read"]),
        "created_at": created.isoformat(timespec="seconds") if created else None,
    }


def notify(
    user_id: int | None,
    notification_type: str,
    *,
    case_id: int | None = None,
    actor_user_id: int | None = None,
    payload: dict[str, Any] | None = None,
    conn: Db | None = None,
) -> int | None:
    """Record one notification. Returns its id, or None if it was skipped.

    Two things are silently skipped rather than treated as errors, because
    every caller would otherwise have to guard for them:

    * no recipient - a case with a free-text defendant has nobody to tell;
    * self-notification - liking your own filing should not ping you.
    """
    if not user_id:
        return None
    if actor_user_id is not None and int(actor_user_id) == int(user_id):
        return None

    with owned(conn) as db:
        result = db.execute(
            "INSERT INTO notifications "
            "(user_id, type, case_id, actor_user_id, payload, is_read, created_at) "
            "VALUES (%s, %s, %s, %s, %s, 0, UTC_TIMESTAMP())",
            (
                user_id,
                notification_type,
                case_id,
                actor_user_id,
                json.dumps(payload, ensure_ascii=False) if payload else None,
            ),
        )
        db.commit_if_owned()
        return result.lastrowid


def list_since(
    user_id: int, since_id: int = 0, *, limit: int = 50, conn: Db | None = None
) -> list[dict[str, Any]]:
    """Everything newer than `since_id`. This is the SSE poll, and also the
    polling fallback's request - one query serves both transports."""
    with owned(conn) as db:
        rows = db.query_all(
            "SELECT n.*, actor.name AS actor_name "
            "FROM notifications n "
            "LEFT JOIN users actor ON actor.id = n.actor_user_id "
            "WHERE n.user_id = %s AND n.id > %s "
            "ORDER BY n.id ASC LIMIT %s",
            (user_id, int(since_id), int(limit)),
        )
    return [shape_notification(row) for row in rows]


def list_recent(
    user_id: int, *, limit: int = 30, unread_only: bool = False, conn: Db | None = None
) -> list[dict[str, Any]]:
    """Newest first, for the bell's dropdown."""
    where = "n.user_id = %s"
    params: list[Any] = [user_id]
    if unread_only:
        where += " AND n.is_read = 0"
    params.append(int(limit))

    with owned(conn) as db:
        rows = db.query_all(
            "SELECT n.*, actor.name AS actor_name "
            "FROM notifications n "
            "LEFT JOIN users actor ON actor.id = n.actor_user_id "
            f"WHERE {where} "
            "ORDER BY n.id DESC LIMIT %s",
            params,
        )
    return [shape_notification(row) for row in rows]


def unread_count(user_id: int, conn: Db | None = None) -> int:
    with owned(conn) as db:
        return int(
            db.query_value(
                "SELECT COUNT(*) FROM notifications WHERE user_id = %s AND is_read = 0",
                (user_id,),
                default=0,
            )
        )


def mark_read(user_id: int, ids: list[int] | None = None, conn: Db | None = None) -> int:
    """Mark some or all of a user's notifications read.

    `user_id` is always in the WHERE clause, so passing someone else's ids
    marks nothing rather than leaking or mutating their state.
    """
    with owned(conn) as db:
        if ids:
            placeholders = ", ".join(["%s"] * len(ids))
            result = db.execute(
                f"UPDATE notifications SET is_read = 1 "
                f"WHERE user_id = %s AND id IN ({placeholders})",
                [user_id, *ids],
            )
        else:
            result = db.execute(
                "UPDATE notifications SET is_read = 1 WHERE user_id = %s AND is_read = 0",
                (user_id,),
            )
        db.commit_if_owned()
        return result.rowcount


def latest_id(user_id: int, conn: Db | None = None) -> int:
    """The cursor a fresh stream should start from, so a newly opened
    connection does not replay the user's whole history."""
    with owned(conn) as db:
        return int(
            db.query_value(
                "SELECT COALESCE(MAX(id), 0) FROM notifications WHERE user_id = %s",
                (user_id,),
                default=0,
            )
        )
