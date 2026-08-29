"""Looking up the court cast.

Pools are returned as plain id lists so jury selection can stay a pure function
with no database access at all.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from ..db import Db, owned


def pool_ids(
    role: str,
    conn: Db | None = None,
    exclude: Iterable[int] | None = None,
) -> list[int]:
    """Active agent ids for a role, sorted, minus anyone disqualified.

    Sorted deliberately: `select_panel` samples from this list, and sorting
    makes the draw depend only on *which* agents exist, never on the order
    MySQL happened to return them in. Without it, an unrelated row update
    could silently change who gets seated on a case.

    `exclude` is how a case keeps its own parties off its own bench. This
    became load-bearing when bots started suing each other: before that a bot
    was never a party to a case, so "the defendant is also juror #4" could not
    arise. Now it can, and a defendant voting on their own guilt is not a joke
    the site is making on purpose.

    Excluding at most two agents cannot starve the draw - the pools are far
    larger than PANEL_SIZE - and `select_panel` returns None (leaving the case
    to retry next tick) if that ever stops being true.
    """
    blocked = {int(x) for x in (exclude or ()) if x is not None}

    with owned(conn) as db:
        rows = db.query_all(
            "SELECT a.user_id FROM agents a JOIN users u ON u.id = a.user_id "
            "WHERE a.role = %s AND a.is_active = 1 AND u.status = 'active' "
            "ORDER BY a.user_id ASC",
            (role,),
        )
    return [int(row["user_id"]) for row in rows if int(row["user_id"]) not in blocked]


def get_agent(user_id: int, conn: Db | None = None) -> dict[str, Any] | None:
    with owned(conn) as db:
        return db.query_one(
            "SELECT a.*, u.name, u.bio, u.avatar_url "
            "FROM agents a JOIN users u ON u.id = a.user_id "
            "WHERE a.user_id = %s",
            (user_id,),
        )


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
