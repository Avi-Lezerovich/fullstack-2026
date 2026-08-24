"""The units of trial work a tick performs.

Each task takes its own connection and commits **per unit of work**, not per
batch. One case that fails to advance must not roll back the four that already
did - and a `LIMIT` on every query means one tick has a predictable worst case
no matter how large the backlog is. A worker that has been down for an hour
catches up over several ticks instead of stalling for minutes on the first.
"""

from __future__ import annotations

import logging

from app.db import connect
from app.services import jury_service, trial_service

log = logging.getLogger(__name__)


def _drain(fetch, act, limit: int) -> int:
    """Claim a batch, then act on each item in its own transaction.

    The batch query holds `FOR UPDATE SKIP LOCKED` locks so two workers split
    the work rather than colliding; the per-item status-guarded UPDATE inside
    `act` is what actually makes a double-run harmless.
    """
    db = connect()
    done = 0
    try:
        for item in fetch(limit, db):
            if act(item, db) == "ok":
                db.commit()
                done += 1
            else:
                # Somebody else got there first, or the item was not ready.
                db.rollback()
        return done
    finally:
        db.close()


def open_filed_cases() -> int:
    """Defensive: give a deadline to anything stuck in 'filed'.

    create_case writes 'witness_phase' directly, so this only ever catches a
    hand-inserted row - but such a row would otherwise sit forever with
    nothing to move it.
    """
    return trial_service.open_filed_cases()


def close_cases(limit: int = 20) -> int:
    """Day 7: retire cases whose verdict has stood long enough."""
    return _drain(
        lambda n, db: trial_service.due_cases("verdict_reached", n, conn=db),
        lambda case, db: trial_service.close_case(case["id"], conn=db),
        limit,
    )


def advance_verdicts(limit: int = 10) -> int:
    """Day 6: tally the jury and let the judge rule."""
    return _drain(
        lambda n, db: trial_service.due_cases("jury_deliberation", n, conn=db),
        lambda case, db: trial_service.advance_to_verdict(case["id"], conn=db),
        limit,
    )


def run_due_jurors(limit: int = 10) -> int:
    """Days 2–5: let each juror speak at the moment assigned at draw time."""
    return _drain(
        lambda n, db: jury_service.due_jurors(n, conn=db),
        lambda member, db: trial_service.speak_as_juror(member, conn=db),
        limit,
    )


def advance_witness_phase(limit: int = 10) -> int:
    """Day 2: close the witness phase and seat a jury."""
    return _drain(
        lambda n, db: trial_service.due_cases("witness_phase", n, conn=db),
        lambda case, db: trial_service.advance_to_deliberation(case["id"], conn=db),
        limit,
    )
