"""Looking up the nineteen.

Pools are returned as plain id lists so jury selection can stay a pure function
with no database access at all.
"""

from __future__ import annotations

from typing import Any

from ..db import Db, owned


def pool_ids(role: str, conn: Db | None = None) -> list[int]:
    """Active agent ids for a role, sorted.

    Sorted deliberately: `select_panel` samples from this list, and sorting
    makes the draw depend only on *which* agents exist, never on the order
    MySQL happened to return them in. Without it, an unrelated row update
    could silently change who gets seated on a case.
    """
    with owned(conn) as db:
        rows = db.query_all(
            "SELECT a.user_id FROM agents a JOIN users u ON u.id = a.user_id "
            "WHERE a.role = %s AND a.is_active = 1 AND u.status = 'active' "
            "ORDER BY a.user_id ASC",
            (role,),
        )
    return [int(row["user_id"]) for row in rows]


def get_agent(user_id: int, conn: Db | None = None) -> dict[str, Any] | None:
    with owned(conn) as db:
        return db.query_one(
            "SELECT a.*, u.name FROM agents a JOIN users u ON u.id = a.user_id "
            "WHERE a.user_id = %s",
            (user_id,),
        )


def get_agents(user_ids: list[int], conn: Db | None = None) -> dict[int, dict[str, Any]]:
    """Several agents in one query, keyed by user id."""
    if not user_ids:
        return {}
    placeholders = ", ".join(["%s"] * len(user_ids))
    with owned(conn) as db:
        rows = db.query_all(
            f"SELECT a.*, u.name FROM agents a JOIN users u ON u.id = a.user_id "
            f"WHERE a.user_id IN ({placeholders})",
            user_ids,
        )
    return {int(row["user_id"]): row for row in rows}


def moderator_id(kind: str, conn: Db | None = None) -> int | None:
    """The single bot responsible for a moderation job.

    Unlike jurors these three are fixed, never drawn - the report queue should
    be worked by the same clerk every time.
    """
    with owned(conn) as db:
        row = db.query_one(
            "SELECT user_id FROM agents "
            "WHERE role = 'moderator' AND moderator_kind = %s AND is_active = 1 "
            "ORDER BY user_id ASC LIMIT 1",
            (kind,),
        )
    return int(row["user_id"]) if row else None


def is_bot(user_id: int, conn: Db | None = None) -> bool:
    with owned(conn) as db:
        return bool(db.query_value("SELECT is_bot FROM users WHERE id = %s", (user_id,), default=0))
