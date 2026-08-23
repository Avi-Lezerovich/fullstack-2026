"""Moderation: the publish-time scan, the report queue, and the audit trail.

Four statuses, identical on cases and comments:

    published   public
    flagged     STILL PUBLIC, marked for review - borderline content is not
                silently removed, and the author is not silenced for one bad word
    hidden      placeholder to the public, full text to the author and to admins
    rejected    the same, set by a toxic scan at publish time

**Nothing here ever issues a DELETE.** Hiding is a status transition, which is
what makes it reversible - and reversibility is the whole point of letting bots
make the first decision. A human admin can put anything back, and the
moderation_actions row records both the previous and the new status so the
override is visible afterwards.

Rejected content is still INSERTED rather than discarded. It never publishes,
so "toxic = rejected" holds, but the evidence survives for the admin queue and
the audit trail stays complete.
"""

from __future__ import annotations

from typing import Any

import pymysql

from ..brain import sentiment
from ..db import Db, owned
from . import auth_service, notifications_service

# target_type -> table. A literal lookup, never interpolated from input.
_TABLES = {"case": "cases", "comment": "comments"}

HIDDEN_STATUSES = ("hidden", "rejected")
VISIBLE_STATUSES = ("published", "flagged")
CONTENT_STATUSES = VISIBLE_STATUSES + HIDDEN_STATUSES

OPEN = "open"
CLAIMED = "claimed"
RESOLVED_HIDDEN = "resolved_hidden"
RESOLVED_DISMISSED = "resolved_dismissed"
RESOLVED_BANNED = "resolved_banned"


# --- publish-time screening -------------------------------------------------


def screen(text: str) -> tuple[str, sentiment.Scan]:
    """(moderation_status, scan) for new content.

    Runs inside the same transaction as the INSERT, which is why it is a
    lexicon and not a model call: every comment would otherwise pay for it.
    """
    scan = sentiment.scan(text or "")
    return sentiment.status_for(scan.label), scan


def record_scan(
    target_type: str,
    target_id: int,
    source: str,
    scan: sentiment.Scan,
    conn: Db | None = None,
) -> None:
    with owned(conn) as db:
        db.execute(
            "INSERT INTO moderation_scans "
            "(target_type, target_id, source, label, score, matched_terms, scanned_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, UTC_TIMESTAMP())",
            (target_type, target_id, source, scan.label, scan.score, scan.matched_terms or None),
        )
        db.commit_if_owned()


# --- content status ---------------------------------------------------------


def get_content(target_type: str, target_id: int, conn: Db | None = None) -> dict[str, Any] | None:
    """The moderated row, whichever table it is in."""
    table = _TABLES.get(target_type)
    if table is None:
        return None
    with owned(conn) as db:
        return db.query_one(
            f"SELECT id, author_id, moderation_status FROM {table} WHERE id = %s", (target_id,)
        )


def set_content_status(
    target_type: str,
    target_id: int,
    new_status: str,
    *,
    actor_id: int,
    actor_is_bot: bool = False,
    action: str | None = None,
    reason: str | None = None,
    notify: bool = True,
    conn: Db | None = None,
) -> str:
    """Move content between statuses and record who did it and why."""
    table = _TABLES.get(target_type)
    if table is None or new_status not in CONTENT_STATUSES:
        return "invalid"

    with owned(conn) as db:
        row = db.query_one(
            f"SELECT id, author_id, moderation_status FROM {table} WHERE id = %s", (target_id,)
        )
        if row is None:
            return "not_found"

        previous = row["moderation_status"]
        if previous == new_status:
            return "already_done"

        db.execute(
            f"UPDATE {table} SET moderation_status = %s, scanned_at = UTC_TIMESTAMP() "
            "WHERE id = %s",
            (new_status, target_id),
        )
        audit(
            actor_id,
            action or _action_for(previous, new_status),
            target_type,
            target_id,
            previous=previous,
            new=new_status,
            reason=reason,
            actor_is_bot=actor_is_bot,
            conn=db.db,
        )

        if notify and new_status in HIDDEN_STATUSES:
            notifications_service.notify(
                row["author_id"],
                "moderation",
                actor_user_id=None,
                payload={
                    "target_type": target_type,
                    "target_id": target_id,
                    "status": new_status,
                    "reason": reason,
                },
                conn=db.db,
            )

        db.commit_if_owned()
        return "ok"


def _action_for(previous: str, new: str) -> str:
    if new in HIDDEN_STATUSES:
        return "reject" if new == "rejected" else "hide"
    if previous in HIDDEN_STATUSES:
        return "unhide"
    return "flag" if new == "flagged" else "unhide"


def audit(
    actor_id: int,
    action: str,
    target_type: str,
    target_id: int,
    *,
    previous: str | None = None,
    new: str | None = None,
    reason: str | None = None,
    actor_is_bot: bool = False,
    conn: Db | None = None,
) -> int:
    """Append to the trail. This is what makes "an admin can override any bot
    decision" auditable rather than merely possible."""
    with owned(conn) as db:
        result = db.execute(
            "INSERT INTO moderation_actions "
            "(actor_user_id, actor_is_bot, action, target_type, target_id, "
            " previous_status, new_status, reason, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, UTC_TIMESTAMP())",
            (actor_id, int(actor_is_bot), action, target_type, target_id, previous, new, reason),
        )
        db.commit_if_owned()
        return result.lastrowid


def history(target_type: str, target_id: int, conn: Db | None = None) -> list[dict[str, Any]]:
    with owned(conn) as db:
        rows = db.query_all(
            "SELECT a.*, u.name AS actor_name FROM moderation_actions a "
            "JOIN users u ON u.id = a.actor_user_id "
            "WHERE a.target_type = %s AND a.target_id = %s ORDER BY a.id DESC",
            (target_type, target_id),
        )
    return [
        {
            "id": row["id"],
            "actor": {"id": row["actor_user_id"], "name": row["actor_name"]},
            "actor_is_bot": bool(row["actor_is_bot"]),
            "action": row["action"],
            "previous_status": row["previous_status"],
            "new_status": row["new_status"],
            "reason": row["reason"],
            "created_at": row["created_at"].isoformat(timespec="seconds"),
        }
        for row in rows
    ]


# --- the report queue -------------------------------------------------------


def report(
    target_type: str,
    target_id: int,
    reporter_id: int,
    reason: str,
    details: str | None = None,
    conn: Db | None = None,
) -> tuple[str, int | None]:
    """File a report. Returns (result, report_id).

    UNIQUE (target_type, target_id, reported_by) means one report per person
    per target, so the queue cannot be flooded by one angry user.
    """
    if target_type not in _TABLES:
        return "invalid", None

    with owned(conn) as db:
        if get_content(target_type, target_id, conn=db.db) is None:
            return "not_found", None
        try:
            result = db.execute(
                "INSERT INTO reports "
                "(target_type, target_id, reported_by, reason, details, status, created_at) "
                "VALUES (%s, %s, %s, %s, %s, 'open', UTC_TIMESTAMP())",
                (target_type, target_id, reporter_id, reason[:64], details),
            )
        except pymysql.err.IntegrityError:
            return "conflict", None
        db.commit_if_owned()
        return "ok", result.lastrowid


def claim_open_reports(clerk_id: int, limit: int = 5, conn: Db | None = None) -> list[dict[str, Any]]:
    """Take the next batch off the queue.

    `AND status = 'open'` in the UPDATE *is* the claim - a second clerk running
    at the same moment updates nothing and gets an empty batch.
    """
    with owned(conn) as db:
        candidates = db.query_all(
            "SELECT id FROM reports WHERE status = 'open' ORDER BY created_at ASC LIMIT %s "
            "FOR UPDATE SKIP LOCKED",
            (int(limit),),
        )
        if not candidates:
            return []

        ids = [row["id"] for row in candidates]
        placeholders = ", ".join(["%s"] * len(ids))
        claimed = db.execute(
            f"UPDATE reports SET status = 'claimed', claimed_by = %s, claimed_at = UTC_TIMESTAMP() "
            f"WHERE id IN ({placeholders}) AND status = 'open'",
            [clerk_id, *ids],
        )
        if claimed.rowcount == 0:
            return []

        rows = db.query_all(
            f"SELECT * FROM reports WHERE id IN ({placeholders}) AND status = 'claimed' "
            "AND claimed_by = %s",
            [*ids, clerk_id],
        )
        db.commit_if_owned()
        return rows


def claimed_reports(limit: int = 10, conn: Db | None = None) -> list[dict[str, Any]]:
    """Reports the clerk could not decide, waiting for the arbiter."""
    with owned(conn) as db:
        return db.query_all(
            "SELECT * FROM reports WHERE status = 'claimed' ORDER BY claimed_at ASC LIMIT %s",
            (int(limit),),
        )


def resolve_report(
    report_id: int,
    status: str,
    *,
    resolver_id: int,
    note: str | None = None,
    conn: Db | None = None,
) -> str:
    with owned(conn) as db:
        result = db.execute(
            "UPDATE reports SET status = %s, resolved_by = %s, resolved_at = UTC_TIMESTAMP(), "
            "  resolution_note = %s "
            "WHERE id = %s AND status IN ('open', 'claimed')",
            (status, resolver_id, (note or "")[:255] or None, report_id),
        )
        db.commit_if_owned()
        return "ok" if result.rowcount == 1 else "already_done"


def target_text(target_type: str, target_id: int, conn: Db | None = None) -> str:
    """The words a scanner should look at, whatever kind of content it is."""
    with owned(conn) as db:
        if target_type == "case":
            row = db.query_one("SELECT title, body FROM cases WHERE id = %s", (target_id,))
            return f"{row['title']}\n{row['body']}" if row else ""
        row = db.query_one("SELECT body FROM comments WHERE id = %s", (target_id,))
        return row["body"] if row else ""


def list_reports(
    status: str | None = None, limit: int = 50, conn: Db | None = None
) -> list[dict[str, Any]]:
    where = ""
    params: list[Any] = []
    if status == "resolved":
        where = "WHERE r.status LIKE 'resolved%%'"
    elif status:
        where = "WHERE r.status = %s"
        params.append(status)
    params.append(int(limit))

    with owned(conn) as db:
        rows = db.query_all(
            "SELECT r.*, reporter.name AS reporter_name, resolver.name AS resolver_name "
            "FROM reports r "
            "JOIN users reporter ON reporter.id = r.reported_by "
            "LEFT JOIN users resolver ON resolver.id = r.resolved_by "
            f"{where} ORDER BY r.created_at DESC LIMIT %s",
            params,
        )
        return [
            {
                "id": row["id"],
                "target_type": row["target_type"],
                "target_id": row["target_id"],
                "reason": row["reason"],
                "details": row["details"],
                "status": row["status"],
                "reporter": {"id": row["reported_by"], "name": row["reporter_name"]},
                "resolver": (
                    {"id": row["resolved_by"], "name": row["resolver_name"]}
                    if row["resolved_by"]
                    else None
                ),
                "resolution_note": row["resolution_note"],
                "created_at": row["created_at"].isoformat(timespec="seconds"),
                "excerpt": target_text(row["target_type"], row["target_id"], conn=db.db)[:200],
            }
            for row in rows
        ]


# --- repeat offenders -------------------------------------------------------


def prior_hides(author_id: int, conn: Db | None = None) -> int:
    """How many of this author's items have been hidden before.

    Counted from the audit trail rather than from a column on users, so it
    stays correct when an admin reverses a decision.
    """
    with owned(conn) as db:
        return int(
            db.query_value(
                "SELECT COUNT(*) FROM moderation_actions a "
                "WHERE a.action IN ('hide', 'reject') "
                "  AND ((a.target_type = 'case' AND a.target_id IN "
                "         (SELECT id FROM cases WHERE author_id = %s)) "
                "    OR (a.target_type = 'comment' AND a.target_id IN "
                "         (SELECT id FROM comments WHERE author_id = %s)))",
                (author_id, author_id),
                default=0,
            )
        )


def ban_user(
    user_id: int, *, actor_id: int, actor_is_bot: bool = False, reason: str | None = None,
    conn: Db | None = None,
) -> str:
    """Ban, and revoke every session in the same transaction.

    Revoking is belt and braces: `resolve_session` also refuses a banned
    account, so the ban bites on the next request either way.
    """
    with owned(conn) as db:
        result = db.execute(
            "UPDATE users SET status = 'banned', banned_at = UTC_TIMESTAMP() "
            "WHERE id = %s AND status = 'active'",
            (user_id,),
        )
        if result.rowcount != 1:
            return "already_done"

        auth_service.delete_all_sessions(user_id, conn=db.db)
        audit(
            actor_id, "ban", "user", user_id, previous="active", new="banned",
            reason=reason, actor_is_bot=actor_is_bot, conn=db.db,
        )
        notifications_service.notify(
            user_id, "moderation", payload={"status": "banned", "reason": reason}, conn=db.db
        )
        db.commit_if_owned()
        return "ok"


def unban_user(user_id: int, *, actor_id: int, conn: Db | None = None) -> str:
    with owned(conn) as db:
        result = db.execute(
            "UPDATE users SET status = 'active', banned_at = NULL "
            "WHERE id = %s AND status = 'banned'",
            (user_id,),
        )
        if result.rowcount != 1:
            return "already_done"
        audit(actor_id, "unban", "user", user_id, previous="banned", new="active", conn=db.db)
        db.commit_if_owned()
        return "ok"


# --- the sweeper's queue ----------------------------------------------------


def unscanned(limit: int = 20, older_than_minutes: int = 1, conn: Db | None = None) -> list[dict]:
    """Published content nobody has scanned yet.

    The age filter avoids racing the publish-time scan on something posted a
    moment ago. `scanned_at` is always stamped afterwards, so each item is
    swept at most once.
    """
    with owned(conn) as db:
        cases = db.query_all(
            "SELECT id, 'case' AS target_type, author_id FROM cases "
            "WHERE scanned_at IS NULL AND created_at < DATE_SUB(UTC_TIMESTAMP(), INTERVAL %s MINUTE) "
            "ORDER BY id ASC LIMIT %s",
            (int(older_than_minutes), int(limit)),
        )
        comments = db.query_all(
            "SELECT id, 'comment' AS target_type, author_id FROM comments "
            "WHERE scanned_at IS NULL AND created_at < DATE_SUB(UTC_TIMESTAMP(), INTERVAL %s MINUTE) "
            "ORDER BY id ASC LIMIT %s",
            (int(older_than_minutes), int(limit)),
        )
    return [*cases, *comments][:limit]


def mark_scanned(target_type: str, target_id: int, conn: Db | None = None) -> None:
    table = _TABLES.get(target_type)
    if table is None:
        return
    with owned(conn) as db:
        db.execute(f"UPDATE {table} SET scanned_at = UTC_TIMESTAMP() WHERE id = %s", (target_id,))
        db.commit_if_owned()


def flagged_content(limit: int = 50, conn: Db | None = None) -> list[dict[str, Any]]:
    """Everything an admin might want to look at, newest first."""
    with owned(conn) as db:
        cases = db.query_all(
            "SELECT c.id, 'case' AS target_type, c.title AS heading, c.body AS body, "
            "       c.moderation_status, c.created_at, u.name AS author_name, c.author_id "
            "FROM cases c JOIN users u ON u.id = c.author_id "
            "WHERE c.moderation_status <> 'published' ORDER BY c.created_at DESC LIMIT %s",
            (int(limit),),
        )
        comments = db.query_all(
            "SELECT cm.id, 'comment' AS target_type, NULL AS heading, cm.body AS body, "
            "       cm.moderation_status, cm.created_at, u.name AS author_name, cm.author_id "
            "FROM comments cm JOIN users u ON u.id = cm.author_id "
            "WHERE cm.moderation_status <> 'published' ORDER BY cm.created_at DESC LIMIT %s",
            (int(limit),),
        )

    items = [*cases, *comments]
    items.sort(key=lambda row: row["created_at"], reverse=True)
    return [
        {
            "target_type": row["target_type"],
            "target_id": row["id"],
            "heading": row["heading"],
            "excerpt": (row["body"] or "")[:200],
            "moderation_status": row["moderation_status"],
            "author": {"id": row["author_id"], "name": row["author_name"]},
            "created_at": row["created_at"].isoformat(timespec="seconds"),
        }
        for row in items[:limit]
    ]
