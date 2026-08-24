"""The three moderator bots.

    clerk    works the human report queue every tick
    arbiter  decides the borderline cases the clerk left, and bans repeat offenders
    sweeper  periodically re-scans published content nobody reported

Unlike jurors these three are fixed rather than drawn: the same clerk works the
queue every time, so the audit trail names a consistent actor.

Every decision they make is reversible. Nothing here deletes; hiding is a
status transition, and moderation_actions records the previous status so a
human admin can see exactly what a bot did and put it back.
"""

from __future__ import annotations

import logging

from app.brain import sentiment
from app.config import get_settings
from app.db import connect
from app.services import agents_service, moderation_service

log = logging.getLogger(__name__)


def _rescan(target_type: str, target_id: int, source: str, db) -> sentiment.Scan:
    text = moderation_service.target_text(target_type, target_id, conn=db)
    scan = sentiment.scan(text)
    moderation_service.record_scan(target_type, target_id, source, scan, conn=db)
    return scan


def work_report_queue(limit: int = 5) -> int:
    """The clerk: claim open reports, re-scan the target, decide the clear ones.

    A borderline result is deliberately NOT resolved here - it is left claimed
    for the arbiter, which is what makes "borderline" mean something rather
    than being rounded to one extreme.
    """
    clerk = agents_service.moderator_id("clerk")
    if clerk is None:
        return 0

    db = connect()
    handled = 0
    try:
        for report in moderation_service.claim_open_reports(clerk, limit, conn=db):
            scan = _rescan(report["target_type"], report["target_id"], "report", db)

            if scan.label == "toxic":
                moderation_service.set_content_status(
                    report["target_type"],
                    report["target_id"],
                    "hidden",
                    actor_id=clerk,
                    actor_is_bot=True,
                    action="hide",
                    reason=f"דיווח משתמש אומת בסריקה: {scan.matched_terms}"[:255],
                    conn=db,
                )
                moderation_service.resolve_report(
                    report["id"],
                    moderation_service.RESOLVED_HIDDEN,
                    resolver_id=clerk,
                    note="התוכן הוסתר בעקבות הדיווח.",
                    conn=db,
                )
            elif scan.label == "ok":
                moderation_service.resolve_report(
                    report["id"],
                    moderation_service.RESOLVED_DISMISSED,
                    resolver_id=clerk,
                    note="נבדק ולא נמצאה חריגה.",
                    conn=db,
                )
                # Tell the reporter their report was looked at and dismissed.
                _notify_reporter(report, db)
            else:
                # Left 'claimed' on purpose: the arbiter decides.
                pass

            db.commit()
            handled += 1
        return handled
    finally:
        db.close()


def _notify_reporter(report, db) -> None:
    from app.services import notifications_service

    notifications_service.notify(
        report["reported_by"],
        "moderation",
        payload={
            "outcome": "dismissed",
            "target_type": report["target_type"],
            "target_id": report["target_id"],
        },
        conn=db,
    )


def arbiter_pass(limit: int = 10) -> int:
    """The arbiter: settle borderline reports, and ban repeat offenders.

    "Repeat offender" is counted from the audit trail rather than from a
    counter on the user, so reversing a bot's decision genuinely un-counts it.
    """
    arbiter = agents_service.moderator_id("arbiter")
    if arbiter is None:
        return 0

    threshold = get_settings().repeat_offender_threshold
    db = connect()
    handled = 0
    try:
        for report in moderation_service.claimed_reports(limit, conn=db):
            content = moderation_service.get_content(
                report["target_type"], report["target_id"], conn=db
            )
            if content is None:
                moderation_service.resolve_report(
                    report["id"],
                    moderation_service.RESOLVED_DISMISSED,
                    resolver_id=arbiter,
                    note="התוכן אינו קיים עוד.",
                    conn=db,
                )
                db.commit()
                handled += 1
                continue

            author_id = content["author_id"]
            moderation_service.set_content_status(
                report["target_type"],
                report["target_id"],
                "hidden",
                actor_id=arbiter,
                actor_is_bot=True,
                action="hide",
                reason="הוכרע על ידי הבורר לאחר דיווח.",
                conn=db,
            )

            offences = moderation_service.prior_hides(author_id, conn=db)
            if offences >= threshold:
                moderation_service.ban_user(
                    author_id,
                    actor_id=arbiter,
                    actor_is_bot=True,
                    reason=f"{offences} פריטים שהוסתרו.",
                    conn=db,
                )
                resolution = moderation_service.RESOLVED_BANNED
                note = "המשתמש הושעה בשל הפרות חוזרות."
            else:
                resolution = moderation_service.RESOLVED_HIDDEN
                note = "התוכן הוסתר."

            moderation_service.resolve_report(
                report["id"], resolution, resolver_id=arbiter, note=note, conn=db
            )
            db.commit()
            handled += 1
        return handled
    finally:
        db.close()


def sweep_unscanned(limit: int = 20) -> int:
    """The sweeper: the safety net for content nobody reported.

    Every item is stamped `scanned_at` whatever the outcome, so nothing is
    swept twice and the queue genuinely drains.
    """
    sweeper = agents_service.moderator_id("sweeper")
    if sweeper is None:
        return 0

    db = connect()
    scanned = 0
    try:
        for item in moderation_service.unscanned(limit, conn=db):
            scan = _rescan(item["target_type"], item["id"], "sweep", db)

            if scan.label == "toxic":
                moderation_service.set_content_status(
                    item["target_type"], item["id"], "hidden",
                    actor_id=sweeper, actor_is_bot=True, action="hide",
                    reason=f"סריקה יזומה: {scan.matched_terms}"[:255], conn=db,
                )
            elif scan.label == "borderline":
                moderation_service.set_content_status(
                    item["target_type"], item["id"], "flagged",
                    actor_id=sweeper, actor_is_bot=True, action="flag",
                    reason="סומן לבדיקה בסריקה יזומה.", notify=False, conn=db,
                )
            else:
                # set_content_status stamps scanned_at, but an unchanged status
                # returns early - so stamp it here or this item is swept forever.
                moderation_service.mark_scanned(item["target_type"], item["id"], conn=db)

            db.commit()
            scanned += 1
        return scanned
    finally:
        db.close()
