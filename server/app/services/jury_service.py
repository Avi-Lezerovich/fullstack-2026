"""Drawing a jury, staggering it, and counting the votes.

`select_panel` is a **pure function**: no database, no clock, no globals. Given
the same pools and the same case it always seats the same seven jurors under
the same judge at the same moments. That is what makes the draw testable, and
what lets a worker that died mid-transition redo the work identically.

The staggering is the interesting part. Each juror is assigned an absolute
moment inside the deliberation window at draw time and it is written to the
database. The worker therefore holds no schedule in memory: it only ever asks
"whose `speaks_at` has passed and who has not spoken yet". Restart it whenever
you like.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import random
from dataclasses import dataclass
from typing import Any

from ..db import Db, owned

PANEL_SIZE = 7

# Jurors speak between 5% and 95% of the way through the window rather than
# across all of it, so nobody speaks in the same instant the panel is drawn or
# at the exact moment the verdict is due.
WINDOW_MARGIN = 0.05


@dataclass(frozen=True)
class Seat:
    seat: int
    juror_user_id: int
    speaks_at: _dt.datetime


@dataclass(frozen=True)
class PanelDraw:
    judge_user_id: int
    seats: tuple[Seat, ...]

    @property
    def juror_ids(self) -> tuple[int, ...]:
        return tuple(seat.juror_user_id for seat in self.seats)


def _rng(salt: str, case_id: int) -> random.Random:
    """Seeded by the case, so the same trial always draws the same court.

    Python's hash() is randomised per process and cannot be used: the web
    process and the worker must agree.
    """
    key = f"{salt}:{case_id}"
    digest = hashlib.blake2b(key.encode("utf-8"), digest_size=8).digest()
    return random.Random(int.from_bytes(digest, "big"))


def select_panel(
    *,
    case_id: int,
    juror_ids: list[int],
    judge_ids: list[int],
    filed_at: _dt.datetime,
    window_start_minutes: int,
    window_end_minutes: int,
    salt: str = "",
) -> PanelDraw | None:
    """Seat seven jurors and a judge. Returns None if the pools are too small.

    Returning None rather than raising lets the worker log a misconfiguration
    and move on; the case stays in the witness phase and the draw is retried
    next tick, so seeding the missing agents fixes it with no intervention.
    """
    if len(juror_ids) < PANEL_SIZE or not judge_ids:
        return None

    rng = _rng(salt, case_id)
    # Sorted before sampling so the result depends on the SET of ids, never on
    # the order the caller happened to supply them in.
    judge_user_id = rng.choice(sorted(judge_ids))
    drawn = rng.sample(sorted(juror_ids), PANEL_SIZE)

    span = max(0, window_end_minutes - window_start_minutes)
    offsets = sorted(
        window_start_minutes + rng.uniform(WINDOW_MARGIN, 1 - WINDOW_MARGIN) * span
        for _ in range(PANEL_SIZE)
    )

    # Offsets are sorted and then zipped to seats, so seat order IS speaking
    # order - which makes the panel read top-to-bottom in the UI and makes
    # assertions about "who spoke first" straightforward.
    seats = tuple(
        Seat(
            seat=index,
            juror_user_id=juror_id,
            speaks_at=filed_at + _dt.timedelta(minutes=offset),
        )
        for index, (juror_id, offset) in enumerate(zip(drawn, offsets))
    )
    return PanelDraw(judge_user_id=judge_user_id, seats=seats)


def tally(guilty: int, not_guilty: int, judge_lean: str | None) -> tuple[str, bool]:
    """Turn the votes into a verdict. Returns (verdict, tiebreak_used).

    With all seven present a tie is arithmetically impossible - the closest is
    4–3 - so the tiebreak only ever fires if a juror is missing a vote. It uses
    the judge's fixed lean rather than a coin flip, which keeps the outcome
    reproducible and testable.
    """
    if guilty > not_guilty:
        return "guilty", False
    if not_guilty > guilty:
        return "not_guilty", False
    return (judge_lean or "not_guilty"), True


# --- persistence ------------------------------------------------------------


def seat_panel(case_id: int, draw: PanelDraw, conn: Db | None = None) -> str:
    """Write a drawn panel. Returns "ok" or "already_done".

    jury_panels has case_id as its PRIMARY KEY, so a second worker attempting
    the same transition collides here and is told the work is done. Panel
    creation is idempotent by construction rather than by checking first.
    """
    with owned(conn) as db:
        inserted = db.execute(
            "INSERT IGNORE INTO jury_panels (case_id, judge_user_id, drawn_at) "
            "VALUES (%s, %s, UTC_TIMESTAMP())",
            (case_id, draw.judge_user_id),
        )
        if inserted.rowcount == 0:
            return "already_done"

        db.execute_many(
            "INSERT INTO jury_panel_members (case_id, juror_user_id, seat, speaks_at) "
            "VALUES (%s, %s, %s, %s)",
            [(case_id, seat.juror_user_id, seat.seat, seat.speaks_at) for seat in draw.seats],
        )
        db.commit_if_owned()
        return "ok"


def get_panel(case_id: int, conn: Db | None = None) -> dict[str, Any] | None:
    with owned(conn) as db:
        return db.query_one(
            "SELECT p.*, u.name AS judge_name, a.personality_name AS judge_personality "
            "FROM jury_panels p "
            "JOIN users u ON u.id = p.judge_user_id "
            "LEFT JOIN agents a ON a.user_id = p.judge_user_id "
            "WHERE p.case_id = %s",
            (case_id,),
        )


def get_members(case_id: int, conn: Db | None = None) -> list[dict[str, Any]]:
    with owned(conn) as db:
        return db.query_all(
            "SELECT m.*, u.name AS juror_name, u.avatar_url, a.personality_name "
            "FROM jury_panel_members m "
            "JOIN users u ON u.id = m.juror_user_id "
            "LEFT JOIN agents a ON a.user_id = m.juror_user_id "
            "WHERE m.case_id = %s ORDER BY m.seat ASC",
            (case_id,),
        )


def due_jurors(limit: int = 10, conn: Db | None = None) -> list[dict[str, Any]]:
    """Jurors whose moment has arrived and who have not spoken.

    FOR UPDATE SKIP LOCKED so two workers partition the batch rather than
    fighting over it. The `spoke_at IS NULL` predicate is the claim.
    """
    with owned(conn) as db:
        return db.query_all(
            "SELECT m.id, m.case_id, m.juror_user_id, m.seat "
            "FROM jury_panel_members m JOIN cases c ON c.id = m.case_id "
            "WHERE m.spoke_at IS NULL "
            "  AND m.speaks_at <= UTC_TIMESTAMP() "
            "  AND c.status = 'jury_deliberation' "
            "ORDER BY m.speaks_at ASC LIMIT %s FOR UPDATE SKIP LOCKED",
            (int(limit),),
        )


def silent_members(case_id: int, conn: Db | None = None) -> list[dict[str, Any]]:
    """Seated jurors who still have not spoken, regardless of their moment.

    Used by the catch-up at verdict time so a worker that was down for the
    entire deliberation window still produces a full seven-juror record.
    """
    with owned(conn) as db:
        return db.query_all(
            "SELECT id, case_id, juror_user_id, seat FROM jury_panel_members "
            "WHERE case_id = %s AND spoke_at IS NULL ORDER BY seat ASC",
            (case_id,),
        )


def record_speech(member_id: int, vote: str, comment_id: int | None, conn: Db | None = None) -> str:
    """Record a juror's vote. Returns "ok" or "already_done".

    The `spoke_at IS NULL` guard is the second, independent idempotency layer:
    even if the comment insert somehow succeeded twice, a juror cannot vote
    twice.
    """
    with owned(conn) as db:
        result = db.execute(
            "UPDATE jury_panel_members SET spoke_at = UTC_TIMESTAMP(), vote = %s, comment_id = %s "
            "WHERE id = %s AND spoke_at IS NULL",
            (vote, comment_id, member_id),
        )
        db.commit_if_owned()
        return "ok" if result.rowcount == 1 else "already_done"


def count_votes(case_id: int, conn: Db | None = None) -> tuple[int, int]:
    """(guilty, not_guilty) among jurors who have actually voted."""
    with owned(conn) as db:
        rows = db.query_all(
            "SELECT vote, COUNT(*) AS n FROM jury_panel_members "
            "WHERE case_id = %s AND vote IS NOT NULL GROUP BY vote",
            (case_id,),
        )
    counts = {row["vote"]: int(row["n"]) for row in rows}
    return counts.get("guilty", 0), counts.get("not_guilty", 0)


def record_tally(
    case_id: int, guilty: int, not_guilty: int, tiebreak_used: bool, conn: Db | None = None
) -> None:
    with owned(conn) as db:
        db.execute(
            "UPDATE jury_panels SET tally_guilty = %s, tally_not_guilty = %s, "
            "  tallied_at = UTC_TIMESTAMP(), tiebreak_used = %s WHERE case_id = %s",
            (guilty, not_guilty, int(tiebreak_used), case_id),
        )
        db.commit_if_owned()
