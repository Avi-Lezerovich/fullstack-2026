"""Likes.

There is no "already liked" check anywhere in this module. The composite
PRIMARY KEY (case_id, user_id) *is* the one-like-per-user rule, so two
simultaneous requests cannot both insert, and the toggle works by asking the
database to delete first and treating "nothing deleted" as "not liked yet".
"""

from __future__ import annotations

from ..db import Db, owned
from . import notifications_service


def toggle_like(case_id: int, user_id: int, conn: Db | None = None) -> tuple[str, dict]:
    """Like if not liked, unlike if liked. Returns (result, {liked, like_count}).

    DELETE-then-maybe-INSERT rather than SELECT-then-decide: the delete's
    rowcount tells us the previous state atomically, with no window in which
    another request could change it underneath us.
    """
    with owned(conn) as db:
        case = db.query_one(
            "SELECT id, author_id, title, moderation_status FROM cases WHERE id = %s",
            (case_id,),
        )
        if case is None or case["moderation_status"] in ("hidden", "rejected"):
            return "not_found", {}

        removed = db.execute(
            "DELETE FROM likes WHERE case_id = %s AND user_id = %s", (case_id, user_id)
        )
        liked = removed.rowcount == 0

        if liked:
            db.execute(
                "INSERT INTO likes (case_id, user_id, created_at) "
                "VALUES (%s, %s, UTC_TIMESTAMP())",
                (case_id, user_id),
            )
            # notify() drops self-notifications, so liking your own filing is
            # silent without a guard here.
            notifications_service.notify(
                case["author_id"],
                "like",
                case_id=case_id,
                actor_user_id=user_id,
                payload={"case_title": case["title"]},
                conn=db.db,
            )

        total = int(
            db.query_value("SELECT COUNT(*) FROM likes WHERE case_id = %s", (case_id,), default=0)
        )
        db.commit_if_owned()
        return "ok", {"liked": liked, "like_count": total}


def has_liked(case_id: int, user_id: int | None, conn: Db | None = None) -> bool:
    if not user_id:
        return False
    with owned(conn) as db:
        return (
            db.query_one(
                "SELECT 1 AS hit FROM likes WHERE case_id = %s AND user_id = %s",
                (case_id, user_id),
            )
            is not None
        )


def likers(case_id: int, *, limit: int = 20, conn: Db | None = None) -> list[dict]:
    with owned(conn) as db:
        rows = db.query_all(
            "SELECT u.id, u.name, u.avatar_url, u.is_bot "
            "FROM likes l JOIN users u ON u.id = l.user_id "
            "WHERE l.case_id = %s ORDER BY l.created_at DESC LIMIT %s",
            (case_id, int(limit)),
        )
    return [
        {
            "id": row["id"],
            "name": row["name"],
            "avatar_url": row["avatar_url"],
            "is_bot": bool(row["is_bot"]),
        }
        for row in rows
    ]
