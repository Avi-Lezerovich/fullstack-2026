"""The case state machine.

    create_case()        day 2                day 6              day 7
[filed] -> [witness_phase] -> [jury_deliberation] -> [verdict_reached] -> [closed]

Every transition below follows the same shape, and the shape is the point:

  1. claim the row (`FOR UPDATE SKIP LOCKED`, or a UNIQUE index);
  2. do the work;
  3. commit with a **status-guarded UPDATE whose rowcount is checked**.

Step 3 is what makes a second worker harmless: it finds the status already
changed, its UPDATE matches nothing, and it abandons the transaction. Combined
with `comments.dedupe_key` and `jury_panels.case_id` being a primary key, two
workers running flat out produce exactly the same final state as one.

None of this depends on the advisory lock the worker also takes. That lock is
an efficiency measure; these guards are the correctness.
"""

from __future__ import annotations

import logging
from typing import Any

from .. import brain
from ..brain import decide
from ..clock import (
    closing_deadline_offset,
    deliberation_window,
    verdict_deadline_offset,
)
from ..config import get_settings
from ..db import Db, owned
from . import (
    agents_service,
    comments_service,
    jury_service,
    notifications_service,
    summons_service,
)

log = logging.getLogger(__name__)

def due_cases(status: str, limit: int = 20, conn: Db | None = None) -> list[dict[str, Any]]:
    """Cases whose current phase has run out.

    SKIP LOCKED so two workers split the batch instead of blocking on each
    other; the status guard on the eventual UPDATE is what keeps it correct.
    """
    with owned(conn) as db:
        return db.query_all(
            "SELECT id FROM cases "
            "WHERE status = %s AND phase_deadline_at IS NOT NULL "
            "  AND phase_deadline_at <= UTC_TIMESTAMP() "
            "ORDER BY phase_deadline_at ASC LIMIT %s FOR UPDATE SKIP LOCKED",
            (status, int(limit)),
        )


def _case_context(case: dict[str, Any], db) -> dict[str, Any]:
    """The flat, JSON-serialisable dict the brain is given.

    Flat because the offline generator hashes it for its seed, and a nested
    structure would make that hash depend on formatting rather than content.
    """
    charges = [
        row["charge"]
        for row in db.query_all(
            "SELECT charge FROM case_charges WHERE case_id = %s ORDER BY id", (case["id"],)
        )
    ]
    testimonies = [
        row["body"][:200]
        for row in db.query_all(
            "SELECT body FROM comments WHERE case_id = %s AND role = 'witness_testimony' "
            "ORDER BY created_at ASC LIMIT 6",
            (case["id"],),
        )
    ]
    # What the room has already heard. Without this every juror wrote into a
    # vacuum: twelve opening statements, none of them aware that anybody else
    # had spoken, several of them making the same observation in a row. A
    # deliberation is a conversation, and this is the only thing that made it
    # readable as one.
    #
    # It moves with the trial, so a juror's *text* is no longer byte-identical
    # across a retry. The juror's VOTE still is - decide_vote reads only the
    # charges and the testimony counts - and the vote is the part the engine
    # stores, tallies and turns into a verdict.
    said_so_far = [
        f"{row['personality_name'] or row['name']}: {row['body'][:200]}"
        for row in db.query_all(
            "SELECT cm.body, u.name, a.personality_name FROM comments cm "
            "JOIN users u ON u.id = cm.author_id "
            "LEFT JOIN agents a ON a.user_id = cm.author_id "
            "WHERE cm.case_id = %s AND cm.role = 'jury_deliberation' "
            "ORDER BY cm.created_at ASC LIMIT 8",
            (case["id"],),
        )
    ]
    plaintiff = db.query_value(
        "SELECT name FROM users WHERE id = %s", (case["author_id"],), default=""
    )
    counts = summons_service.counts_by_side(case["id"], conn=db.db)

    return {
        "case_id": case["id"],
        "case_title": case["title"],
        "case_body": (case["body"] or "")[:600],
        "defendant": case["defendant_text"],
        "plaintiff": plaintiff,
        "charges": charges,
        "testimonies": testimonies,
        "discussion": said_so_far,
        # Testimony for the defence pushes a juror away from conviction.
        "testimony_for": counts[summons_service.DEFENSE],
        "testimony_against": counts[summons_service.PLAINTIFF],
    }


# --- witness phase -> jury deliberation -------------------------------------


def advance_to_deliberation(case_id: int, conn: Db | None = None) -> str:
    """Close the witness phase and seat a jury.

    On any non-"ok" result the caller must abandon the transaction: nothing is
    committed here except on success.
    """
    settings = get_settings()
    with owned(conn) as db:
        case = db.query_one("SELECT * FROM cases WHERE id = %s FOR UPDATE", (case_id,))
        if case is None:
            return "not_found"
        if case["status"] != "witness_phase":
            return "already_done"

        summons_service.mark_no_shows(case_id, conn=db.db)

        window_start, window_end = deliberation_window()

        # Nobody sits in judgement of a case they are a party to. Bots sue each
        # other now, so the author and the defendant can both be agents - and
        # without this the defendant could be drawn onto their own jury, or
        # preside over their own trial.
        parties = (case["author_id"], case["defendant_user_id"])
        draw = jury_service.select_panel(
            case_id=case_id,
            juror_ids=agents_service.pool_ids("juror", conn=db.db, exclude=parties),
            judge_ids=agents_service.pool_ids("judge", conn=db.db, exclude=parties),
            filed_at=case["filed_at"],
            window_start_minutes=window_start,
            window_end_minutes=window_end,
            salt=settings.jury_seed_salt,
        )
        if draw is None:
            # Not enough agents seeded. Leave the case where it is and retry
            # next tick, so seeding the missing bots fixes it unattended.
            log.warning("case %s cannot be seated: the agent pools are too small", case_id)
            return "no_pool"

        if jury_service.seat_panel(case_id, draw, conn=db.db) == "already_done":
            return "already_done"

        moved = db.execute(
            "UPDATE cases SET status = 'jury_deliberation', "
            "  phase_deadline_at = DATE_ADD(filed_at, INTERVAL %s MINUTE) "
            "WHERE id = %s AND status = 'witness_phase'",
            (verdict_deadline_offset(), case_id),
        )
        if moved.rowcount != 1:
            return "already_done"

        db.commit_if_owned()
        return "ok"


# --- one juror speaks -------------------------------------------------------


def speak_as_juror(member: dict[str, Any], conn: Db | None = None) -> str:
    """Post one juror's deliberation and record their vote.

    Idempotent on two independent levels. `comments.dedupe_key` makes a second
    comment physically impossible; `record_speech`'s `spoke_at IS NULL` guard
    makes a second vote impossible. Neither relies on the other, so a crash
    between the two recovers cleanly: the retry finds the existing comment and
    finishes the vote.
    """
    settings = get_settings()
    with owned(conn) as db:
        case = db.query_one("SELECT * FROM cases WHERE id = %s", (member["case_id"],))
        agent = agents_service.get_agent(member["juror_user_id"], conn=db.db)
        if case is None or agent is None:
            return "not_found"

        context = _case_context(case, db)

        # The vote is decided, not parsed out of the text. Both are seeded from
        # the same inputs, so a retry reaches the same conclusion.
        vote = decide.decide_vote(
            guilt_bias=float(agent["guilt_bias"]),
            case_id=case["id"],
            juror_user_id=member["juror_user_id"],
            salt=settings.jury_seed_salt,
            context=context,
        )
        text = brain.generate(agent["personality_prompt"], "jury_deliberation", context)

        result, comment_id = comments_service.create_comment(
            case["id"],
            member["juror_user_id"],
            text,
            role="jury_deliberation",
            dedupe_key=f"jury:{member['id']}",
            # Court speech is not screened at publish time, nor picked up
            # later by the sweeper.
            #
            # This was once justified by "it comes from our own corpus", which
            # a live model backend made untrue. It stands now for a different
            # and stronger reason: a rejected verdict has nowhere to go. The
            # caller treats any result other than ok/already_done as a failure
            # and retries the tick, so a screened-out verdict would wedge the
            # case in jury_deliberation forever. Bot lawsuits and bot comments
            # ARE screened - they can simply be dropped.
            screen=False,
            scanned=True,
            notify_author=False,  # seven jurors would mean seven pings per case
            conn=db.db,
        )
        if result not in ("ok", "already_done"):
            return result

        recorded = jury_service.record_speech(member["id"], vote, comment_id, conn=db.db)
        db.commit_if_owned()
        return recorded


# --- jury deliberation -> verdict -------------------------------------------


def advance_to_verdict(case_id: int, conn: Db | None = None) -> str:
    """Tally the jury and let the judge rule."""
    with owned(conn) as db:
        case = db.query_one("SELECT * FROM cases WHERE id = %s FOR UPDATE", (case_id,))
        if case is None:
            return "not_found"
        if case["status"] != "jury_deliberation":
            return "already_done"

        panel = jury_service.get_panel(case_id, conn=db.db)
        if panel is None:
            return "not_found"

        # Catch-up: any juror who never got their moment speaks now. This is
        # what guarantees a full seven-juror record even if the worker was
        # down for the entire deliberation window.
        for member in jury_service.silent_members(case_id, conn=db.db):
            speak_as_juror(member, conn=db.db)

        guilty, not_guilty = jury_service.count_votes(case_id, conn=db.db)
        judge = agents_service.get_agent(panel["judge_user_id"], conn=db.db)
        judge_lean = judge["tiebreak_lean"] if judge else None

        verdict, tiebreak_used = jury_service.tally(guilty, not_guilty, judge_lean)

        context = _case_context(case, db)
        context.update(
            {"verdict": verdict, "tally_guilty": guilty, "tally_not_guilty": not_guilty}
        )

        judge_prompt = judge["personality_prompt"] if judge else ""
        verdict_text = brain.generate(judge_prompt, "verdict", context)
        sentence_text = (
            brain.generate(judge_prompt, "sentence", context) if verdict == "guilty" else None
        )

        body = verdict_text if not sentence_text else f"{verdict_text}\n\n{sentence_text}"
        result, comment_id = comments_service.create_comment(
            case_id,
            panel["judge_user_id"],
            body,
            role="verdict",
            dedupe_key=f"verdict:{case_id}",
            screen=False,
            scanned=True,
            notify_author=False,  # the verdict notification below is richer
            conn=db.db,
        )
        if result not in ("ok", "already_done"):
            return result

        jury_service.record_tally(case_id, guilty, not_guilty, tiebreak_used, conn=db.db)

        moved = db.execute(
            "UPDATE cases SET status = 'verdict_reached', verdict = %s, sentence_text = %s, "
            "  verdict_at = UTC_TIMESTAMP(), "
            "  phase_deadline_at = DATE_ADD(filed_at, INTERVAL %s MINUTE) "
            "WHERE id = %s AND status = 'jury_deliberation'",
            (verdict, sentence_text, closing_deadline_offset(), case_id),
        )
        if moved.rowcount != 1:
            return "already_done"

        _notify_verdict(db, case, verdict, sentence_text, comment_id)
        db.commit_if_owned()
        return "ok"


def _notify_verdict(db, case, verdict, sentence_text, comment_id) -> None:
    """Tell everyone with a stake: both parties, and every witness who showed."""
    payload = {
        "case_title": case["title"],
        "verdict": verdict,
        "sentence_text": sentence_text,
        "comment_id": comment_id,
    }
    recipients = {case["author_id"], case["defendant_user_id"]}
    witnesses = db.query_all(
        "SELECT witness_user_id FROM witness_summons "
        "WHERE case_id = %s AND status = 'testified'",
        (case["id"],),
    )
    recipients.update(row["witness_user_id"] for row in witnesses)

    for user_id in recipients:
        notifications_service.notify(
            user_id, "verdict", case_id=case["id"], payload=payload, conn=db.db
        )


# --- verdict -> closed ------------------------------------------------------


def close_case(case_id: int, conn: Db | None = None) -> str:
    """Retire the case.

    The badge becomes permanent and trial actions end. Likes and comments stay
    open forever - closing the file does not close the discussion.
    """
    with owned(conn) as db:
        moved = db.execute(
            "UPDATE cases SET status = 'closed', closed_at = UTC_TIMESTAMP(), "
            "  phase_deadline_at = NULL "
            "WHERE id = %s AND status = 'verdict_reached'",
            (case_id,),
        )
        if moved.rowcount != 1:
            return "already_done"
        db.commit_if_owned()
        return "ok"


def open_filed_cases(limit: int = 20, conn: Db | None = None) -> int:
    """Defensive sweep for anything stuck in 'filed'.

    create_case writes 'witness_phase' directly, so this only ever picks up a
    hand-inserted row - but a case with no deadline would otherwise sit there
    forever with nothing to move it.
    """
    from ..clock import witness_deadline_offset

    with owned(conn) as db:
        moved = db.execute(
            "UPDATE cases SET status = 'witness_phase', "
            "  phase_deadline_at = DATE_ADD(filed_at, INTERVAL %s MINUTE) "
            "WHERE status = 'filed' LIMIT %s",
            (witness_deadline_offset(), int(limit)),
        )
        db.commit_if_owned()
        return moved.rowcount
