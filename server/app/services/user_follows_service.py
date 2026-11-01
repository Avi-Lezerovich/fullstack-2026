"""User follows - which people a user keeps an eye on.

The person-to-person sibling of `follows_service`, which tracks cases. The
point of following somebody is "My Feed": every case they file shows up there
beside the cases you follow one at a time. That query lives in
`cases_service.list_feed_cases`, next to the case-follow one it extends.

The composite PRIMARY KEY (follower_id, followee_id) is the "follow once" rule,
and `toggle` mirrors `follows_service.toggle_follow` down to the
DELETE-then-maybe-INSERT: the delete's rowcount IS the previous state.

No notification is sent, for the same reason a case follow sends none.
"""

from __future__ import annotations

from ..db import Db, owned


def toggle(follower_id: int, followee_id: int, *, conn: Db | None = None) -> tuple[str, dict]:
    """Follow if not following, unfollow if following.

    Returns ("ok", {"following": bool, "follower_count": int}), ("invalid", {})
    for following yourself, or ("not_found", {}) for somebody who does not
    exist or is banned.

    The count is read back inside the same transaction as the write, so the
    number the button shows is the number the database holds.
    """
    if follower_id == followee_id:
        return "invalid", {}

    with owned(conn) as db:
        target = db.query_one("SELECT id, status FROM users WHERE id = %s", (followee_id,))
        if target is None or target["status"] == "banned":
            return "not_found", {}

        removed = db.execute(
            "DELETE FROM user_follows WHERE follower_id = %s AND followee_id = %s",
            (follower_id, followee_id),
        )
        following = removed.rowcount == 0

        if following:
            db.execute(
                "INSERT INTO user_follows (follower_id, followee_id, created_at) "
                "VALUES (%s, %s, UTC_TIMESTAMP())",
                (follower_id, followee_id),
            )

        total = follower_count(followee_id, conn=db)
        db.commit_if_owned()
        return "ok", {"following": following, "follower_count": total}


def is_following(follower_id: int | None, followee_id: int, *, conn: Db | None = None) -> bool:
    """Whether this viewer follows this person. Anonymous viewers follow nobody."""
    if not follower_id:
        return False
    with owned(conn) as db:
        row = db.query_one(
            "SELECT 1 AS hit FROM user_follows WHERE follower_id = %s AND followee_id = %s",
            (follower_id, followee_id),
        )
    return row is not None


def follower_count(user_id: int, *, conn: Db | None = None) -> int:
    """How many people follow this person. Banned accounts are left out, as
    they are from `followers`, so the number and the list agree."""
    with owned(conn) as db:
        return int(
            db.query_value(
                "SELECT COUNT(*) FROM user_follows f JOIN users u ON u.id = f.follower_id "
                "WHERE f.followee_id = %s AND u.status <> 'banned'",
                (user_id,),
                default=0,
            )
        )


def followee_count(user_id: int, *, conn: Db | None = None) -> int:
    """How many people this person follows."""
    with owned(conn) as db:
        return int(
            db.query_value(
                "SELECT COUNT(*) FROM user_follows f JOIN users u ON u.id = f.followee_id "
                "WHERE f.follower_id = %s AND u.status <> 'banned'",
                (user_id,),
                default=0,
            )
        )


def _user_list(sql: str, user_id: int, limit: int, db) -> list[dict]:
    rows = db.query_all(sql, (user_id, int(limit)))
    return [
        {
            "id": row["id"],
            "name": row["name"],
            "avatar_url": row["avatar_url"],
            "is_bot": bool(row["is_bot"]),
        }
        for row in rows
    ]


def followers(user_id: int, *, limit: int = 50, conn: Db | None = None) -> list[dict]:
    """Who follows this person, newest first. Shaped like `follows_service.followers`
    so the same dialog renders both."""
    with owned(conn) as db:
        return _user_list(
            "SELECT u.id, u.name, u.avatar_url, u.is_bot "
            "FROM user_follows f JOIN users u ON u.id = f.follower_id "
            "WHERE f.followee_id = %s AND u.status <> 'banned' "
            "ORDER BY f.created_at DESC LIMIT %s",
            user_id,
            limit,
            db,
        )


def followees(user_id: int, *, limit: int = 50, conn: Db | None = None) -> list[dict]:
    """Who this person follows, newest first."""
    with owned(conn) as db:
        return _user_list(
            "SELECT u.id, u.name, u.avatar_url, u.is_bot "
            "FROM user_follows f JOIN users u ON u.id = f.followee_id "
            "WHERE f.follower_id = %s AND u.status <> 'banned' "
            "ORDER BY f.created_at DESC LIMIT %s",
            user_id,
            limit,
            db,
        )
