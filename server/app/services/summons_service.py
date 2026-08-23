"""Witness summons.

Five rules, all enforced on the server, each with its own test:

1. only during the witness phase;
2. only a party to the case may summon (the plaintiff always, the defendant
   only when they are a registered user);
3. a witness must be a HUMAN - the nineteen bots are the court, not evidence;
4. a witness may not be a party to their own case;
5. at most three per side, and nobody twice.

Rule 5's "nobody twice" is a UNIQUE index rather than a check, so two
simultaneous summons cannot both slip through.
"""

from __future__ import annotations

from typing import Any

import pymysql

from ..db import Db, owned
from . import comments_service, notifications_service

MAX_WITNESSES_PER_SIDE = 3

PLAINTIFF = "plaintiff"
DEFENSE = "defense"


def side_for(case: dict[str, Any], user_id: int) -> str | None:
    """Which side this user is on, or None if they are not a party."""
    if case["author_id"] == user_id:
        return PLAINTIFF
    if case["defendant_user_id"] and case["defendant_user_id"] == user_id:
        return DEFENSE
    return None


def shape_summons(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "case_id": row["case_id"],
        "witness": {
            "id": row["witness_user_id"],
            "name": row.get("witness_name"),
            "avatar_url": row.get("witness_avatar"),
            "is_bot": False,
        },
        "summoned_by_user_id": row["summoned_by_user_id"],
        "side": row["side"],
        "status": row["status"],
        "deadline_at": row["deadline_at"].isoformat(timespec="seconds")
        if row.get("deadline_at")
        else None,
        "responded_at": row["responded_at"].isoformat(timespec="seconds")
        if row.get("responded_at")
        else None,
        "testimony_comment_id": row.get("testimony_comment_id"),
    }


def summon(
    case_id: int, summoner_id: int, witness_id: int, conn: Db | None = None
) -> tuple[str, int | None]:
    """Summon a witness. Returns (result, summons_id)."""
    with owned(conn) as db:
        case = db.query_one(
            "SELECT id, author_id, defendant_user_id, status, phase_deadline_at, title "
            "FROM cases WHERE id = %s",
            (case_id,),
        )
        if case is None:
            return "not_found", None

        # Rule 1 - phase.
        if case["status"] != "witness_phase":
            return "closed", None

        # Rule 2 - only a party may summon.
        side = side_for(case, summoner_id)
        if side is None:
            return "forbidden", None

        witness = db.query_one("SELECT id, is_bot, status FROM users WHERE id = %s", (witness_id,))
        if witness is None or witness["status"] != "active":
            return "not_found", None

        # Rule 3 - witnesses are human. The bots are the court itself; letting
        # a juror testify in a case it may later judge would be absurd.
        if witness["is_bot"]:
            return "invalid", None

        # Rule 4 - parties are not witnesses to their own case.
        if side_for(case, witness_id) is not None:
            return "invalid", None

        # Rule 5a - three per side.
        used = int(
            db.query_value(
                "SELECT COUNT(*) FROM witness_summons WHERE case_id = %s AND side = %s",
                (case_id, side),
                default=0,
            )
        )
        if used >= MAX_WITNESSES_PER_SIDE:
            return "conflict", None

        try:
            # Rule 5b - no duplicates. UNIQUE (case_id, witness_user_id) is the
            # enforcement; this is not a check-then-insert.
            #
            # deadline_at is copied from the case so the row is self-describing
            # and a witness can see their own deadline without a join.
            result = db.execute(
                "INSERT INTO witness_summons "
                "(case_id, witness_user_id, summoned_by_user_id, side, status, "
                " summoned_at, deadline_at) "
                "VALUES (%s, %s, %s, %s, 'pending', UTC_TIMESTAMP(), %s)",
                (case_id, witness_id, summoner_id, side, case["phase_deadline_at"]),
            )
        except pymysql.err.IntegrityError:
            return "conflict", None

        notifications_service.notify(
            witness_id,
            "summons",
            case_id=case_id,
            actor_user_id=summoner_id,
            payload={"case_title": case["title"], "side": side},
            conn=db.db,
        )
        db.commit_if_owned()
        return "ok", result.lastrowid


def testify(
    case_id: int, witness_id: int, body: str, conn: Db | None = None
) -> tuple[str, int | None]:
    """Give testimony. Returns (result, comment_id).

    Testimony is a comment with role='witness_testimony' - the same table, the
    same threading, the same moderation as anything else anybody says.
    """
    with owned(conn) as db:
        case = db.query_one("SELECT id, status FROM cases WHERE id = %s", (case_id,))
        if case is None:
            return "not_found", None
        if case["status"] != "witness_phase":
            return "closed", None

        summons = db.query_one(
            "SELECT id, status FROM witness_summons "
            "WHERE case_id = %s AND witness_user_id = %s",
            (case_id, witness_id),
        )
        # Only a summoned witness may testify - otherwise it is a comment.
        if summons is None:
            return "forbidden", None
        if summons["status"] != "pending":
            return "conflict", None

        result, comment_id = comments_service.create_comment(
            case_id, witness_id, body, role="witness_testimony", conn=db.db
        )
        if result != "ok":
            return result, None

        db.execute(
            "UPDATE witness_summons SET status = 'testified', responded_at = UTC_TIMESTAMP(), "
            "  testimony_comment_id = %s "
            "WHERE id = %s AND status = 'pending'",
            (comment_id, summons["id"]),
        )
        db.commit_if_owned()
        return "ok", comment_id


def mark_no_shows(case_id: int, conn: Db | None = None) -> int:
    """Close the witness phase: everyone still pending did not appear.

    Each is told, because "you were summoned and missed it" is exactly the
    kind of thing a notification is for.
    """
    with owned(conn) as db:
        pending = db.query_all(
            "SELECT id, witness_user_id FROM witness_summons "
            "WHERE case_id = %s AND status = 'pending'",
            (case_id,),
        )
        if not pending:
            return 0

        db.execute(
            "UPDATE witness_summons SET status = 'no_show', responded_at = UTC_TIMESTAMP() "
            "WHERE case_id = %s AND status = 'pending'",
            (case_id,),
        )
        for row in pending:
            notifications_service.notify(
                row["witness_user_id"],
                "summons",
                case_id=case_id,
                payload={"outcome": "no_show"},
                conn=db.db,
            )
        db.commit_if_owned()
        return len(pending)


def list_for_case(case_id: int, conn: Db | None = None) -> list[dict[str, Any]]:
    with owned(conn) as db:
        rows = db.query_all(
            "SELECT s.*, u.name AS witness_name, u.avatar_url AS witness_avatar "
            "FROM witness_summons s JOIN users u ON u.id = s.witness_user_id "
            "WHERE s.case_id = %s ORDER BY s.side ASC, s.summoned_at ASC",
            (case_id,),
        )
    return [shape_summons(row) for row in rows]


def pending_for_user(user_id: int, conn: Db | None = None) -> list[dict[str, Any]]:
    """Open summonses, so a witness can find the cases waiting on them."""
    with owned(conn) as db:
        rows = db.query_all(
            "SELECT s.*, c.title AS case_title, u.name AS witness_name, "
            "       u.avatar_url AS witness_avatar "
            "FROM witness_summons s "
            "JOIN cases c ON c.id = s.case_id "
            "JOIN users u ON u.id = s.witness_user_id "
            "WHERE s.witness_user_id = %s AND s.status = 'pending' "
            "  AND c.status = 'witness_phase' "
            "ORDER BY s.deadline_at ASC",
            (user_id,),
        )
    return [{**shape_summons(row), "case_title": row["case_title"]} for row in rows]


def counts_by_side(case_id: int, conn: Db | None = None) -> dict[str, int]:
    with owned(conn) as db:
        rows = db.query_all(
            "SELECT side, COUNT(*) AS n FROM witness_summons WHERE case_id = %s GROUP BY side",
            (case_id,),
        )
    counts = {row["side"]: int(row["n"]) for row in rows}
    return {PLAINTIFF: counts.get(PLAINTIFF, 0), DEFENSE: counts.get(DEFENSE, 0)}
