"""Follows - which lawsuits a user keeps an eye on.

The composite PRIMARY KEY (case_id, user_id) on `case_follows` is the "follow
once" rule, exactly as it is for `likes`, so nothing here reads before it
writes.

Two doors into the table. `toggle_follow` is the user tapping the button, and
mirrors `likes_service.toggle_like` down to the DELETE-then-maybe-INSERT: the
delete's rowcount IS the previous state. `follow` is the automatic path - you
filed the case, you were named its defendant, you testified in it - and is a
plain upsert that no-ops on conflict, so it never downgrades a 'manual' row to
'auto'.

An explicit unfollow deletes the row outright. A later auto-trigger re-follows,
which is the simple behaviour and the intended one: there is no "muted" state
to keep in step.

No notification is sent. A follow is a private bookmark, unlike a like.
"""

from __future__ import annotations

from ..db import Db, owned


def toggle_follow(case_id: int, user_id: int, *, conn: Db | None = None) -> tuple[str, dict]:
    """Follow if not following, unfollow if following.

    Returns ("ok", {"following": bool}), or ("not_found", {}) for a case that
    does not exist or is not visible.
    """
    with owned(conn) as db:
        case = db.query_one(
            "SELECT id, moderation_status FROM cases WHERE id = %s", (case_id,)
        )
        if case is None or case["moderation_status"] in ("hidden", "rejected"):
            return "not_found", {}

        removed = db.execute(
            "DELETE FROM case_follows WHERE case_id = %s AND user_id = %s",
            (case_id, user_id),
        )
        following = removed.rowcount == 0

        if following:
            db.execute(
                "INSERT INTO case_follows (case_id, user_id, source, created_at) "
                "VALUES (%s, %s, 'manual', UTC_TIMESTAMP())",
                (case_id, user_id),
            )

        db.commit_if_owned()
        return "ok", {"following": following}


def follow(
    case_id: int, user_id: int, *, source: str = "auto", conn: Db | None = None
) -> None:
    """Add a follow if there is not one already. Idempotent.

    The automatic paths call this, so it must be safe to run again on a retried
    tick. A row that already exists is left exactly as it is - which is what
    keeps a 'manual' follow from being relabelled 'auto' behind the user's back.
    """
    with owned(conn) as db:
        db.execute(
            "INSERT INTO case_follows (case_id, user_id, source, created_at) "
            "VALUES (%s, %s, %s, UTC_TIMESTAMP()) "
            "ON DUPLICATE KEY UPDATE case_id = case_id",
            (case_id, user_id, source),
        )
        db.commit_if_owned()


def is_following(case_id: int, user_id: int | None, *, conn: Db | None = None) -> bool:
    """Whether this viewer follows this case. Anonymous viewers follow nothing."""
    if not user_id:
        return False
    with owned(conn) as db:
        row = db.query_one(
            "SELECT 1 AS hit FROM case_follows WHERE case_id = %s AND user_id = %s",
            (case_id, user_id),
        )
    return row is not None


def followed_case_ids(user_id: int, *, conn: Db | None = None) -> set[int]:
    """Every case this user follows."""
    with owned(conn) as db:
        rows = db.query_all(
            "SELECT case_id FROM case_follows WHERE user_id = %s", (user_id,)
        )
    return {row["case_id"] for row in rows}
