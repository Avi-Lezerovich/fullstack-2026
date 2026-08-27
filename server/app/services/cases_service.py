"""Cases - a filed lawsuit and the trial attached to it.

A case may name a registered user as defendant (which unlocks defence
witnesses and a verdict that lands on a real account) or keep the defendant as
free text, so "התביעה נגד יום שני" works too.

Filing puts the case straight into `witness_phase` with an absolute deadline.
`filed` exists in the enum for fidelity but is written by nothing - there is no
moment worth modelling between "submitted" and "open for witnesses".
"""

from __future__ import annotations

from typing import Any

from ..clock import witness_deadline_offset
from ..db import Db, owned
from . import moderation_service

MAX_CHARGES = 5
CHARGE_MAX_LENGTH = 64
TITLE_MAX_LENGTH = 512

# The one place "what may the public see" is expressed. Every read query uses
# it, so hiding content cannot be forgotten in some forgotten corner.
# Note that 'flagged' IS public: borderline content stays up, marked for review.
PUBLIC_VISIBILITY = "c.moderation_status IN ('published', 'flagged')"

_CASE_COLUMNS = """
    c.id, c.title, c.body, c.image_url, c.author_id,
    c.defendant_text, c.defendant_user_id,
    c.status, c.phase_deadline_at, c.filed_at,
    c.verdict, c.sentence_text, c.verdict_at, c.closed_at,
    c.moderation_status, c.created_at,
    author.name AS author_name, author.avatar_url AS author_avatar,
    author.is_bot AS author_is_bot,
    defendant.name AS defendant_name, defendant.avatar_url AS defendant_avatar,
    defendant.is_bot AS defendant_is_bot
"""

_CASE_JOINS = """
    FROM cases c
    JOIN users author ON author.id = c.author_id
    LEFT JOIN users defendant ON defendant.id = c.defendant_user_id
"""


def _iso(value) -> str | None:
    return value.isoformat(timespec="seconds") if value else None


def shape_case(
    row: dict[str, Any] | None,
    *,
    charges: list[str] | None = None,
    like_count: int = 0,
    comment_count: int = 0,
    viewer_has_liked: bool = False,
) -> dict[str, Any] | None:
    """Row -> the JSON the client receives. Pure; mirrored by types.ts."""
    if row is None:
        return None
    return {
        "id": row["id"],
        "title": row["title"],
        "body": row["body"],
        "image_url": row["image_url"],
        "author": {
            "id": row["author_id"],
            "name": row["author_name"],
            "avatar_url": row["author_avatar"],
            "is_bot": bool(row["author_is_bot"]),
        },
        "defendant_text": row["defendant_text"],
        "defendant": (
            {
                "id": row["defendant_user_id"],
                "name": row["defendant_name"],
                "avatar_url": row["defendant_avatar"],
                "is_bot": bool(row["defendant_is_bot"]),
            }
            if row["defendant_user_id"]
            else None
        ),
        "charges": charges or [],
        "status": row["status"],
        "phase_deadline_at": _iso(row["phase_deadline_at"]),
        "filed_at": _iso(row["filed_at"]),
        "verdict": row["verdict"],
        "sentence_text": row["sentence_text"],
        "verdict_at": _iso(row["verdict_at"]),
        "closed_at": _iso(row["closed_at"]),
        "moderation_status": row["moderation_status"],
        "created_at": _iso(row["created_at"]),
        "like_count": int(like_count),
        "comment_count": int(comment_count),
        "viewer_has_liked": bool(viewer_has_liked),
    }


def clean_charges(charges: Any) -> list[str]:
    """Trim, cap length, drop blanks and duplicates, keep at most MAX_CHARGES."""
    if not isinstance(charges, (list, tuple)):
        return []
    seen: list[str] = []
    for raw in charges:
        text = str(raw).strip()[:CHARGE_MAX_LENGTH]
        if text and text not in seen:
            seen.append(text)
        if len(seen) >= MAX_CHARGES:
            break
    return seen


def _charges_for(case_ids: list[int], db) -> dict[int, list[str]]:
    """All charges for a page of cases in one query, rather than N."""
    if not case_ids:
        return {}
    placeholders = ", ".join(["%s"] * len(case_ids))
    rows = db.query_all(
        f"SELECT case_id, charge FROM case_charges WHERE case_id IN ({placeholders}) "
        "ORDER BY id",
        case_ids,
    )
    grouped: dict[int, list[str]] = {case_id: [] for case_id in case_ids}
    for row in rows:
        grouped[row["case_id"]].append(row["charge"])
    return grouped


def _counts_for(case_ids: list[int], viewer_id: int | None, db) -> dict[int, dict[str, Any]]:
    """Like and comment totals, plus whether the viewer already liked."""
    if not case_ids:
        return {}
    placeholders = ", ".join(["%s"] * len(case_ids))

    likes = db.query_all(
        f"SELECT case_id, COUNT(*) AS n FROM likes WHERE case_id IN ({placeholders}) "
        "GROUP BY case_id",
        case_ids,
    )
    comments = db.query_all(
        f"SELECT case_id, COUNT(*) AS n FROM comments "
        f"WHERE case_id IN ({placeholders}) "
        "  AND moderation_status IN ('published', 'flagged') "
        "GROUP BY case_id",
        case_ids,
    )
    liked_ids: set[int] = set()
    if viewer_id:
        rows = db.query_all(
            f"SELECT case_id FROM likes WHERE user_id = %s AND case_id IN ({placeholders})",
            [viewer_id, *case_ids],
        )
        liked_ids = {row["case_id"] for row in rows}

    like_map = {row["case_id"]: int(row["n"]) for row in likes}
    comment_map = {row["case_id"]: int(row["n"]) for row in comments}
    return {
        case_id: {
            "like_count": like_map.get(case_id, 0),
            "comment_count": comment_map.get(case_id, 0),
            "viewer_has_liked": case_id in liked_ids,
        }
        for case_id in case_ids
    }


# --- writes -----------------------------------------------------------------


def create_case(
    author_id: int,
    title: str,
    body: str,
    defendant_text: str,
    *,
    defendant_user_id: int | None = None,
    charges: list[str] | None = None,
    image_url: str | None = None,
    moderation_status: str | None = None,
    screen: bool = True,
    conn: Db | None = None,
) -> tuple[str, int | None]:
    """File a lawsuit. Returns (result, case_id); "rejected" if it is toxic.

    The witness deadline is computed by the database from its own clock, so the
    worker (in another container, with another clock) can never disagree about
    when the phase ends.

    Rejected filings are still INSERTED, then reported as "rejected" so the
    route answers 422. They never publish, but the evidence survives for the
    admin queue and the audit trail stays complete.
    """
    if not title.strip() or not body.strip() or not defendant_text.strip():
        return "invalid", None

    # MySQL will not let this be a CHECK constraint, because defendant_user_id
    # is written by a foreign key's ON DELETE SET NULL (error 3823). So the rule
    # lives here, and tests/unit/test_cases_rules.py covers it.
    if defendant_user_id is not None and int(defendant_user_id) == int(author_id):
        return "invalid", None

    # The scan runs in the SAME transaction as the insert, so content can
    # never be briefly visible before it is judged.
    scan = None
    if screen and moderation_status is None:
        moderation_status, scan = moderation_service.screen(f"{title}\n{body}")
    elif moderation_status is None:
        moderation_status = "published"

    with owned(conn) as db:
        result = db.execute(
            "INSERT INTO cases "
            "(title, body, author_id, defendant_text, defendant_user_id, image_url, "
            " status, filed_at, phase_deadline_at, moderation_status, scanned_at, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, "
            "        'witness_phase', UTC_TIMESTAMP(), "
            "        DATE_ADD(UTC_TIMESTAMP(), INTERVAL %s MINUTE), "
            "        %s, "
            "        CASE WHEN %s THEN UTC_TIMESTAMP() ELSE NULL END, "
            "        UTC_TIMESTAMP())",
            (
                title.strip()[:TITLE_MAX_LENGTH],
                body.strip(),
                author_id,
                defendant_text.strip(),
                defendant_user_id,
                image_url,
                witness_deadline_offset(),
                moderation_status,
                int(scan is not None),
            ),
        )
        case_id = result.lastrowid

        cleaned = clean_charges(charges)
        if cleaned:
            db.execute_many(
                "INSERT INTO case_charges (case_id, charge) VALUES (%s, %s)",
                [(case_id, charge) for charge in cleaned],
            )

        if scan is not None:
            moderation_service.record_scan("case", case_id, "publish", scan, conn=db.db)

        db.commit_if_owned()
        return ("rejected" if moderation_status == "rejected" else "ok"), case_id


def delete_case(case_id: int, user_id: int, conn: Db | None = None) -> str:
    """Withdraw a filing.

    Only the author, and only while the case is still in the witness phase -
    once a jury has been seated the record belongs to the court. An admin is
    not offered this either: moderation hides, it never deletes.
    """
    with owned(conn) as db:
        row = db.query_one("SELECT author_id, status FROM cases WHERE id = %s", (case_id,))
        if row is None:
            return "not_found"
        if row["author_id"] != user_id:
            return "forbidden"
        if row["status"] not in ("filed", "witness_phase"):
            return "closed"

        db.execute("DELETE FROM cases WHERE id = %s", (case_id,))
        db.commit_if_owned()
        return "ok"


# --- reads ------------------------------------------------------------------


def get_case(
    case_id: int,
    *,
    viewer_id: int | None = None,
    viewer_is_admin: bool = False,
    conn: Db | None = None,
) -> dict[str, Any] | None:
    """One case. Hidden content is visible to its author and to admins only."""
    with owned(conn) as db:
        row = db.query_one(f"SELECT {_CASE_COLUMNS} {_CASE_JOINS} WHERE c.id = %s", (case_id,))
        if row is None:
            return None

        hidden = row["moderation_status"] in ("hidden", "rejected")
        if hidden and not viewer_is_admin and row["author_id"] != viewer_id:
            return None

        charges = _charges_for([case_id], db).get(case_id, [])
        counts = _counts_for([case_id], viewer_id, db)[case_id]
        return shape_case(row, charges=charges, **counts)


def list_cases(
    *,
    viewer_id: int | None = None,
    author_id: int | None = None,
    status: str | None = None,
    limit: int = 20,
    offset: int = 0,
    conn: Db | None = None,
) -> list[dict[str, Any]]:
    where = [PUBLIC_VISIBILITY]
    params: list[Any] = []
    if author_id is not None:
        where.append("c.author_id = %s")
        params.append(author_id)
    if status:
        where.append("c.status = %s")
        params.append(status)
    params.extend([int(limit), int(offset)])

    with owned(conn) as db:
        rows = db.query_all(
            f"SELECT {_CASE_COLUMNS} {_CASE_JOINS} "
            f"WHERE {' AND '.join(where)} "
            "ORDER BY c.created_at DESC, c.id DESC "
            "LIMIT %s OFFSET %s",
            params,
        )
        case_ids = [row["id"] for row in rows]
        charges = _charges_for(case_ids, db)
        counts = _counts_for(case_ids, viewer_id, db)

    return [
        shape_case(row, charges=charges.get(row["id"], []), **counts[row["id"]])
        for row in rows
    ]


def count_cases(
    *, author_id: int | None = None, status: str | None = None, conn: Db | None = None
) -> int:
    """How many cases a matching list_cases() would find.

    The filters must be the SAME ones list_cases applies, or the caller cannot
    use this to decide whether there is another page: the feed compares the
    rows it holds against this number, and a total counted over a wider set
    leaves a "load more" button that can never load anything.
    """
    where = [PUBLIC_VISIBILITY]
    params: list[Any] = []
    if author_id is not None:
        where.append("c.author_id = %s")
        params.append(author_id)
    if status:
        where.append("c.status = %s")
        params.append(status)
    with owned(conn) as db:
        return int(
            db.query_value(
                f"SELECT COUNT(*) FROM cases c WHERE {' AND '.join(where)}", params, default=0
            )
        )


def get_raw(case_id: int, conn: Db | None = None) -> dict[str, Any] | None:
    """The bare row, for the trial engine - no shaping, no visibility rules."""
    with owned(conn) as db:
        return db.query_one("SELECT * FROM cases WHERE id = %s", (case_id,))
