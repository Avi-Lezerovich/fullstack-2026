"""Case activity - the one timestamp a follower's feed sorts on.

`case_activity` holds one row per case: when something worth surfacing last
happened on it, and what that was. Every write goes through `touch()`, called
from inside the transaction that performs the event itself, so a case can never
claim activity that was rolled back.

What counts as activity is a product decision, not a technical one: a comment, a
testimony, a juror's line, a phase change, a verdict, a close. A like does not -
liking a case says something about the liker, not about the case moving on.
"""

from __future__ import annotations

from ..db import Db, owned


def touch(case_id: int, kind: str, *, conn: Db | None = None) -> None:
    """Record that something happened on a case. Upsert; last writer wins.

    `kind` is a free-form slug the caller already knows ('filed', 'comment',
    'testimony', 'deliberation', 'phase', 'verdict', 'closed'). Nothing branches
    on it; it is stored so the UI can one day say what the activity was.

    Pass the caller's `conn` so the bump joins their transaction and commits
    with the event that caused it.
    """
    with owned(conn) as db:
        db.execute(
            "INSERT INTO case_activity (case_id, last_activity_at, last_activity_kind) "
            "VALUES (%s, UTC_TIMESTAMP(), %s) "
            "ON DUPLICATE KEY UPDATE last_activity_at = UTC_TIMESTAMP(), "
            "  last_activity_kind = VALUES(last_activity_kind)",
            (case_id, kind),
        )
        db.commit_if_owned()
