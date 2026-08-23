"""Comments - and every other thing anybody says on a case.

One table holds regular comments, witness testimony, juror deliberation and
the judge's verdict, distinguished by `role`. The UI styles by role; the
storage, threading, moderation and notification paths are identical for all of
them, which is exactly why they share a table.

`dedupe_key` is what makes the trial engine crash-safe. Bot-authored content
passes a deterministic key ('jury:<member_id>', 'verdict:<case_id>'); the
UNIQUE index then makes a duplicate physically impossible, so a worker that
dies after the INSERT but before recording the vote cannot post twice on
retry. Human comments leave it NULL, and MySQL allows unlimited NULLs in a
UNIQUE index.
"""

from __future__ import annotations

from typing import Any

import pymysql

from ..db import Db, owned
from . import moderation_service, notifications_service

# Replies deeper than this are flattened onto their parent. Three levels is as
# far as an indented thread stays readable on a phone.
MAX_DEPTH = 3
BODY_MAX_LENGTH = 4000

ROLES = ("user", "witness_testimony", "jury_deliberation", "verdict")

# The same public-visibility rule cases_service uses. 'flagged' stays visible.
PUBLIC_VISIBILITY = "cm.moderation_status IN ('published', 'flagged')"

_COMMENT_COLUMNS = """
    cm.id, cm.case_id, cm.author_id, cm.parent_comment_id, cm.root_comment_id,
    cm.depth, cm.body, cm.role, cm.moderation_status, cm.created_at,
    u.name AS author_name, u.avatar_url AS author_avatar, u.is_bot AS author_is_bot,
    a.personality_name
"""

_COMMENT_JOINS = """
    FROM comments cm
    JOIN users u ON u.id = cm.author_id
    LEFT JOIN agents a ON a.user_id = cm.author_id
"""


def shape_comment(row: dict[str, Any], *, can_see_hidden: bool = False) -> dict[str, Any]:
    """Row -> API JSON.

    Hidden content is returned as a placeholder rather than omitted, so a
    thread does not silently lose its shape when one reply is removed. The
    body itself is only included for the author and for admins.
    """
    hidden = row["moderation_status"] in ("hidden", "rejected")
    created = row.get("created_at")
    return {
        "id": row["id"],
        "case_id": row["case_id"],
        "author": {
            "id": row["author_id"],
            "name": row["author_name"],
            "avatar_url": row["author_avatar"],
            "is_bot": bool(row["author_is_bot"]),
            "personality_name": row.get("personality_name"),
        },
        "parent_comment_id": row["parent_comment_id"],
        "root_comment_id": row["root_comment_id"],
        "depth": int(row["depth"]),
        "body": None if (hidden and not can_see_hidden) else row["body"],
        "role": row["role"],
        "moderation_status": row["moderation_status"],
        "is_hidden": hidden,
        "created_at": created.isoformat(timespec="seconds") if created else None,
    }


def create_comment(
    case_id: int,
    author_id: int,
    body: str,
    *,
    role: str = "user",
    parent_comment_id: int | None = None,
    dedupe_key: str | None = None,
    moderation_status: str | None = None,
    scanned: bool = False,
    screen: bool = True,
    notify_author: bool = True,
    conn: Db | None = None,
) -> tuple[str, int | None]:
    """Add a comment. Returns (result, comment_id).

    "already_done" means a bot-authored comment with this dedupe_key already
    exists - the retry of a tick that crashed after inserting. The existing id
    is returned so the caller can carry on and finish the rest of its work.

    "rejected" means the publish-time scan blocked it: the row is still
    written (so the admin queue keeps the evidence) but is never public, and
    the route answers 422.
    """
    body = (body or "").strip()[:BODY_MAX_LENGTH]
    if not body:
        return "invalid", None
    if role not in ROLES:
        return "invalid", None

    # Court speech - jurors, judges - is not user content and is stamped as
    # already scanned by its caller, so the sweeper leaves it alone.
    scan = None
    if moderation_status is None:
        if screen:
            moderation_status, scan = moderation_service.screen(body)
        else:
            moderation_status = "published"

    with owned(conn) as db:
        case = db.query_one(
            "SELECT id, author_id, defendant_user_id, title FROM cases WHERE id = %s",
            (case_id,),
        )
        if case is None:
            return "not_found", None

        depth = 0
        root_comment_id: int | None = None
        if parent_comment_id:
            parent = db.query_one(
                "SELECT id, case_id, depth, root_comment_id FROM comments WHERE id = %s",
                (parent_comment_id,),
            )
            if parent is None or parent["case_id"] != case_id:
                return "invalid", None
            # Beyond MAX_DEPTH a reply attaches to the deepest allowed ancestor
            # rather than being refused - the user's words are not the problem.
            depth = min(int(parent["depth"]) + 1, MAX_DEPTH)
            root_comment_id = parent["root_comment_id"] or parent["id"]

        try:
            result = db.execute(
                "INSERT INTO comments "
                "(case_id, author_id, parent_comment_id, root_comment_id, depth, body, "
                " role, moderation_status, scanned_at, dedupe_key, created_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, "
                "        CASE WHEN %s THEN UTC_TIMESTAMP() ELSE NULL END, %s, UTC_TIMESTAMP())",
                (
                    case_id,
                    author_id,
                    parent_comment_id,
                    root_comment_id,
                    depth,
                    body,
                    role,
                    moderation_status,
                    int(scanned or scan is not None),
                    dedupe_key,
                ),
            )
        except pymysql.err.IntegrityError:
            # Only reachable via dedupe_key: the UNIQUE index refused a second
            # copy of work that was already done.
            existing = db.query_one(
                "SELECT id FROM comments WHERE dedupe_key = %s", (dedupe_key,)
            )
            if existing:
                return "already_done", int(existing["id"])
            raise

        comment_id = result.lastrowid

        if root_comment_id is None:
            # A top-level comment is its own thread root, which lets one
            # indexed query fetch and order a whole thread.
            db.execute(
                "UPDATE comments SET root_comment_id = id WHERE id = %s", (comment_id,)
            )

        if scan is not None:
            moderation_service.record_scan("comment", comment_id, "publish", scan, conn=db.db)

        if notify_author and moderation_status not in ("hidden", "rejected"):
            _notify_participants(db, case, comment_id, author_id, role, body)

        db.commit_if_owned()
        return ("rejected" if moderation_status == "rejected" else "ok"), comment_id


def _notify_participants(db, case, comment_id, author_id, role, body) -> None:
    """Tell the people with a stake in this case that something was said.

    notify() drops self-notifications, so commenting on your own case is
    silent without a guard here.
    """
    notification_type = "testimony" if role == "witness_testimony" else "comment"
    payload = {
        "case_title": case["title"],
        "comment_id": comment_id,
        "role": role,
        "excerpt": body[:120],
    }
    for recipient in (case["author_id"], case["defendant_user_id"]):
        notifications_service.notify(
            recipient,
            notification_type,
            case_id=case["id"],
            actor_user_id=author_id,
            payload=payload,
            conn=db.db,
        )


def list_for_case(
    case_id: int,
    *,
    viewer_id: int | None = None,
    viewer_is_admin: bool = False,
    roles: tuple[str, ...] | None = None,
    conn: Db | None = None,
) -> list[dict[str, Any]]:
    """A whole case's thread, ordered so replies follow their root.

    Hidden entries are included as placeholders (see shape_comment) so the
    conversation keeps its shape.
    """
    where = ["cm.case_id = %s"]
    params: list[Any] = [case_id]
    if roles:
        placeholders = ", ".join(["%s"] * len(roles))
        where.append(f"cm.role IN ({placeholders})")
        params.extend(roles)

    with owned(conn) as db:
        rows = db.query_all(
            f"SELECT {_COMMENT_COLUMNS} {_COMMENT_JOINS} "
            f"WHERE {' AND '.join(where)} "
            "ORDER BY COALESCE(cm.root_comment_id, cm.id) ASC, cm.created_at ASC, cm.id ASC",
            params,
        )

    return [
        shape_comment(
            row, can_see_hidden=viewer_is_admin or row["author_id"] == viewer_id
        )
        for row in rows
    ]


def count_for_case(case_id: int, conn: Db | None = None) -> int:
    with owned(conn) as db:
        return int(
            db.query_value(
                "SELECT COUNT(*) FROM comments cm "
                f"WHERE cm.case_id = %s AND {PUBLIC_VISIBILITY}",
                (case_id,),
                default=0,
            )
        )


def get_comment(comment_id: int, conn: Db | None = None) -> dict[str, Any] | None:
    with owned(conn) as db:
        return db.query_one("SELECT * FROM comments WHERE id = %s", (comment_id,))


def find_by_dedupe_key(dedupe_key: str, conn: Db | None = None) -> int | None:
    with owned(conn) as db:
        row = db.query_one("SELECT id FROM comments WHERE dedupe_key = %s", (dedupe_key,))
        return int(row["id"]) if row else None
