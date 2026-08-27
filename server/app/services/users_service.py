"""Users - humans, admins and bots alike.

A bot is an ordinary row here plus a row in `agents`. That is what gives the
nineteen court personalities real profiles: they can be searched for, visited,
liked and messaged exactly like anyone else.
"""

from __future__ import annotations

from typing import Any

import pymysql

from ..db import Db, owned

# Everything the API is willing to say about a user in public.
PUBLIC_COLUMNS = (
    "u.id, u.name, u.bio, u.avatar_url, u.is_admin, u.is_bot, u.status, u.created_at"
)


def public_user(row: dict[str, Any] | None) -> dict[str, Any] | None:
    """Shape a users row for the API. Pure - no database access.

    Never includes the password hash or the email address; a user's email is
    private even from signed-in strangers.
    """
    if row is None:
        return None
    created = row.get("created_at")
    return {
        "id": row["id"],
        "name": row["name"],
        "bio": row.get("bio"),
        "avatar_url": row.get("avatar_url"),
        "is_admin": bool(row.get("is_admin")),
        "is_bot": bool(row.get("is_bot")),
        "status": row.get("status", "active"),
        "created_at": created.isoformat(timespec="seconds") if created else None,
    }


def private_user(row: dict[str, Any] | None) -> dict[str, Any] | None:
    """As public_user, plus the fields a user may see about themselves."""
    shaped = public_user(row)
    if shaped is not None and row is not None:
        shaped["email"] = row.get("email")
    return shaped


def create_user(
    name: str,
    email: str,
    password_hash: str,
    *,
    bio: str | None = None,
    avatar_url: str | None = None,
    is_admin: bool = False,
    is_bot: bool = False,
    conn: Db | None = None,
) -> tuple[str, int | None]:
    """Insert a user. Returns ("ok", id) or ("conflict", None) if the email is
    already registered - the UNIQUE index is what decides, not a prior SELECT,
    so two simultaneous signups cannot both succeed."""
    with owned(conn) as db:
        try:
            result = db.execute(
                "INSERT INTO users "
                "(name, email, password_hash, bio, avatar_url, is_admin, is_bot, "
                " status, created_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, 'active', UTC_TIMESTAMP())",
                (name, email, password_hash, bio, avatar_url, int(is_admin), int(is_bot)),
            )
        except pymysql.err.IntegrityError:
            return "conflict", None
        db.commit_if_owned()
        return "ok", result.lastrowid


def get_by_email(email: str, conn: Db | None = None) -> dict[str, Any] | None:
    with owned(conn) as db:
        return db.query_one("SELECT * FROM users WHERE email = %s", (email,))


def get_by_id(user_id: int, conn: Db | None = None) -> dict[str, Any] | None:
    with owned(conn) as db:
        return db.query_one("SELECT * FROM users WHERE id = %s", (user_id,))


def set_password(user_id: int, password_hash: str, conn: Db | None = None) -> str:
    with owned(conn) as db:
        result = db.execute(
            "UPDATE users SET password_hash = %s WHERE id = %s", (password_hash, user_id)
        )
        db.commit_if_owned()
        return "ok" if result.rowcount else "not_found"


def set_status(user_id: int, status: str, conn: Db | None = None) -> str:
    """Ban or reinstate. Revoking the sessions of a banned user is the caller's
    job (moderation_service does it in the same transaction)."""
    if status not in ("active", "banned"):
        return "invalid"
    with owned(conn) as db:
        result = db.execute(
            "UPDATE users SET status = %s, banned_at = "
            "CASE WHEN %s = 'banned' THEN UTC_TIMESTAMP() ELSE NULL END "
            "WHERE id = %s",
            (status, status, user_id),
        )
        db.commit_if_owned()
        return "ok" if result.rowcount else "not_found"


def update_profile(
    user_id: int,
    *,
    name: str | None = None,
    bio: str | None = None,
    avatar_url: str | None = None,
    conn: Db | None = None,
) -> str:
    """Partial update. Only the fields actually supplied are written.

    None means "not supplied" and is skipped. An empty STRING means "clear
    it", and is stored as NULL rather than "" - the difference is not
    cosmetic: `<Avatar src="">` asks the browser for an empty URL, so an
    emptied avatar field would render as a broken image instead of falling
    back to the user's initials.
    """
    sets: list[str] = []
    params: list[Any] = []
    if name is not None:
        sets.append("name = %s")
        params.append(name)
    if bio is not None:
        sets.append("bio = %s")
        params.append(bio or None)
    if avatar_url is not None:
        sets.append("avatar_url = %s")
        params.append(avatar_url or None)
    if not sets:
        return "ok"

    params.append(user_id)
    with owned(conn) as db:
        # The column names above are literals in this file, never user input.
        db.execute(f"UPDATE users SET {', '.join(sets)} WHERE id = %s", params)
        db.commit_if_owned()
        return "ok"


def _search_where(
    query: str,
    include_bots: bool,
    exclude_ids: tuple[int, ...],
    status: str,
) -> tuple[list[str], list[Any]]:
    """The WHERE shared by search_users and count_users.

    Built once so the list and its total can never disagree about what they
    are looking at - a page that counts more rows than it can ever show is
    exactly the bug this shape prevents.
    """
    where = ["u.status = %s"]
    params: list[Any] = [status]
    if query:
        where.append("u.name LIKE %s")
        params.append(f"%{query}%")
    if not include_bots:
        where.append("u.is_bot = 0")
    if exclude_ids:
        placeholders = ", ".join(["%s"] * len(exclude_ids))
        where.append(f"u.id NOT IN ({placeholders})")
        params.extend(exclude_ids)
    return where, params


def count_users(
    query: str = "",
    *,
    include_bots: bool = True,
    exclude_ids: tuple[int, ...] = (),
    status: str = "active",
    conn: Db | None = None,
) -> int:
    where, params = _search_where(query, include_bots, exclude_ids, status)
    with owned(conn) as db:
        return int(
            db.query_value(
                f"SELECT COUNT(*) FROM users u WHERE {' AND '.join(where)}", params, default=0
            )
        )


def search_users(
    query: str = "",
    *,
    limit: int = 20,
    offset: int = 0,
    include_bots: bool = True,
    exclude_ids: tuple[int, ...] = (),
    status: str = "active",
    conn: Db | None = None,
) -> list[dict[str, Any]]:
    """A page of people.

    `status` is a parameter rather than a hardcoded 'active' so the admin
    dashboard can list suspended accounts - otherwise a ban is irreversible
    through the UI, because a banned user is invisible to every search.
    """
    where, params = _search_where(query, include_bots, exclude_ids, status)
    params.extend([int(limit), int(offset)])
    with owned(conn) as db:
        rows = db.query_all(
            f"SELECT {PUBLIC_COLUMNS} FROM users u "
            f"WHERE {' AND '.join(where)} "
            "ORDER BY u.is_bot ASC, u.name ASC "
            "LIMIT %s OFFSET %s",
            params,
        )
    return [public_user(row) for row in rows]
