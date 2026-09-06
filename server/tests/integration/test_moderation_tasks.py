# -*- coding: utf-8 -*-
"""The three moderator bots, against the real report queue.

    clerk    works the human report queue every tick
    arbiter  decides what the clerk left, and bans repeat offenders
    sweeper  re-scans published content nobody reported

The interesting one is the clerk, and specifically what it does with
`borderline`: **nothing**. It hides `toxic` and dismisses `ok`, and a
borderline result is deliberately left `claimed` for the arbiter. That is what
makes "borderline" a real third answer rather than one of the other two rounded
off - and it is invisible from the outside, because a left-alone report looks
exactly like one the clerk has not reached yet. Only the `status` column tells
them apart, which is why these are database tests.

The second thing worth pinning is the sweeper's `mark_scanned` on the `ok`
branch. `set_content_status` stamps `scanned_at` as a side effect, but returns
early when the status has not changed - so content the sweeper judged fine
would never be stamped, would come back in the next `unscanned()` batch, and
would be re-scanned forever. The comment in the source says so; nothing checked
it.

These run against the seeded cast, because `moderator_id("clerk")` returning
None makes every task here a no-op that returns 0 and asserts nothing.
"""

from __future__ import annotations

import pytest

from app.services import agents_service, moderation_service as mod
from worker import moderation_tasks

pytestmark = [pytest.mark.worker, pytest.mark.integration]

# Drawn from app/brain/sentiment.py's lexicon, which is what these bots read.
TOXIC = "אני אהרוג אותך חתיכת מפגר"
BORDERLINE = "אתה מגעיל ובהמה"
HARMLESS = "אני חולק על הטענה הזו לחלוטין"


@pytest.fixture
def author(make_user):
    return make_user("הכותב", "author@lolsuit.test")


@pytest.fixture
def reporter(make_user):
    return make_user("המדווחת", "reporter@lolsuit.test")


@pytest.fixture
def clerk(db):
    return agents_service.moderator_id("clerk", conn=db)


@pytest.fixture
def arbiter(db):
    return agents_service.moderator_id("arbiter", conn=db)


def _reported_case(db, make_case, author, reporter, body: str) -> int:
    case_id = make_case(author["id"], body=body)
    mod.report("case", case_id, reporter["id"], "abuse", conn=db)
    db.commit()
    return case_id


def _status(db, case_id: int) -> str:
    return db.query_value("SELECT moderation_status FROM cases WHERE id = %s", (case_id,))


def _report_status(db, case_id: int) -> str:
    return db.query_value("SELECT status FROM reports WHERE target_id = %s", (case_id,))


# --- the cast has to exist --------------------------------------------------


def test_the_seed_provides_exactly_one_bot_for_each_moderation_job(db):
    """These three are fixed rather than drawn, so the trail names a consistent
    actor.

    A missing one is not an error anywhere - every task simply returns 0 - so
    without this the whole file could pass while doing nothing at all.
    """
    kinds = {kind: agents_service.moderator_id(kind, conn=db) for kind in ("clerk", "arbiter", "sweeper")}

    assert all(user_id is not None for user_id in kinds.values()), kinds
    assert len(set(kinds.values())) == 3


def test_every_task_is_a_harmless_no_op_when_its_bot_is_missing(db, monkeypatch):
    """A misconfigured deployment must not crash the tick.

    `safe()` in the loop would swallow an exception anyway, but returning 0 is
    what lets the summary say honestly that nothing was moderated.
    """
    monkeypatch.setattr(agents_service, "moderator_id", lambda *a, **k: None)

    assert moderation_tasks.work_report_queue() == 0
    assert moderation_tasks.arbiter_pass() == 0
    assert moderation_tasks.sweep_unscanned() == 0


# --- the clerk --------------------------------------------------------------


def test_the_clerk_hides_a_report_the_scan_confirms(db, make_case, author, reporter, clerk):
    """A user report plus a toxic re-scan is enough to act on unattended."""
    case_id = _reported_case(db, make_case, author, reporter, TOXIC)

    assert moderation_tasks.work_report_queue() == 1

    assert _status(db, case_id) == "hidden"
    assert _report_status(db, case_id) == mod.RESOLVED_HIDDEN

    trail = mod.history("case", case_id, conn=db)
    assert trail[0]["action"] == "hide"
    assert trail[0]["actor_is_bot"] is True
    assert trail[0]["actor"]["id"] == clerk


def test_the_clerk_dismisses_a_report_the_scan_does_not_support(
    db, make_case, author, reporter
):
    """Being reported is not itself evidence.

    Otherwise a single motivated user could hide anything by reporting it.
    """
    case_id = _reported_case(db, make_case, author, reporter, HARMLESS)

    assert moderation_tasks.work_report_queue() == 1

    assert _status(db, case_id) == "published"
    assert _report_status(db, case_id) == mod.RESOLVED_DISMISSED


def test_a_dismissed_report_is_answered_so_the_reporter_knows_it_was_read(
    db, make_case, author, reporter
):
    """Silence would look identical to a queue nobody works.

    Only the dismissal is announced - a confirmed report announces itself by
    the content disappearing.
    """
    _reported_case(db, make_case, author, reporter, HARMLESS)

    moderation_tasks.work_report_queue()

    row = db.query_one(
        "SELECT type, payload FROM notifications WHERE user_id = %s", (reporter["id"],)
    )
    assert row["type"] == "moderation"
    assert "dismissed" in row["payload"]


def test_the_clerk_leaves_a_borderline_report_claimed_for_the_arbiter(
    db, make_case, author, reporter
):
    """The whole reason "borderline" is a third label rather than a rounding.

    The clerk declined to decide, and `claimed` is how it says so. Rounding it
    to `ok` would let hostile content through; rounding it to `toxic` would
    hide content on one hostile adjective.
    """
    case_id = _reported_case(db, make_case, author, reporter, BORDERLINE)

    assert moderation_tasks.work_report_queue() == 1

    assert _status(db, case_id) == "published"
    assert _report_status(db, case_id) == mod.CLAIMED
    assert db.query_value("SELECT COUNT(*) FROM notifications") == 0


def test_the_clerk_records_a_scan_for_every_report_it_touches(
    db, make_case, author, reporter
):
    """`moderation_scans` is the evidence behind an automated decision.

    Without it a moderator reviewing a bot's hide can see that it scored badly
    and not why, which is not enough to overturn it on.
    """
    case_id = _reported_case(db, make_case, author, reporter, TOXIC)

    moderation_tasks.work_report_queue()

    row = db.query_one("SELECT * FROM moderation_scans WHERE target_id = %s", (case_id,))
    assert row["source"] == "report"
    assert row["label"] == "toxic"
    assert row["matched_terms"]


def test_the_clerk_takes_at_most_its_batch_size_in_one_tick(
    db, make_case, author, make_user
):
    """A `LIMIT` on every claim means one tick has a predictable worst case.

    A backlog is caught up over several ticks rather than stalling the first
    one for minutes.
    """
    case_id = make_case(author["id"], body=TOXIC)
    for index in range(5):
        reporter = make_user(f"מדווח {index}", f"reporter{index}@lolsuit.test")
        mod.report("case", case_id, reporter["id"], "abuse", conn=db)
    db.commit()

    assert moderation_tasks.work_report_queue(limit=2) == 2

    assert db.query_value("SELECT COUNT(*) FROM reports WHERE status = 'open'") == 3


def test_running_the_clerk_twice_does_not_re_decide_what_it_already_settled(
    db, make_case, author, reporter
):
    """The claim is the idempotency: a resolved report is no longer open.

    Which means a tick that runs twice - or two workers - reach the same place.
    """
    case_id = _reported_case(db, make_case, author, reporter, TOXIC)

    assert moderation_tasks.work_report_queue() == 1
    assert moderation_tasks.work_report_queue() == 0

    assert db.query_value(
        "SELECT COUNT(*) FROM moderation_actions WHERE target_id = %s AND action = 'hide'",
        (case_id,),
    ) == 1


# --- the arbiter ------------------------------------------------------------


def test_the_arbiter_settles_what_the_clerk_left(db, make_case, author, reporter, arbiter):
    """The second half of the borderline path, and the reason it exists."""
    case_id = _reported_case(db, make_case, author, reporter, BORDERLINE)
    moderation_tasks.work_report_queue()
    assert _report_status(db, case_id) == mod.CLAIMED

    assert moderation_tasks.arbiter_pass() == 1

    assert _status(db, case_id) == "hidden"
    assert _report_status(db, case_id) == mod.RESOLVED_HIDDEN
    assert mod.history("case", case_id, conn=db)[0]["actor"]["id"] == arbiter


def test_the_arbiter_bans_at_the_threshold_and_not_before(
    db, make_case, author, reporter, make_user, monkeypatch
):
    """Two hides is a bad week; three is a pattern.

    The threshold is configuration rather than a constant precisely so it can
    be tightened without a deploy - so it is read at call time and tested that
    way.
    """
    monkeypatch.setenv("REPEAT_OFFENDER_THRESHOLD", "3")

    cases = [make_case(author["id"], body=BORDERLINE, title=f"תביעה {index}") for index in range(3)]
    for index, case_id in enumerate(cases):
        witness = make_user(f"מדווח {index}", f"reporter{index}@lolsuit.test")
        mod.report("case", case_id, witness["id"], "abuse", conn=db)
    db.commit()

    moderation_tasks.work_report_queue(limit=10)

    # First two hides: below the threshold, so no ban.
    moderation_tasks.arbiter_pass(limit=2)
    assert db.query_value("SELECT status FROM users WHERE id = %s", (author["id"],)) == "active"

    # The third takes the count to three.
    moderation_tasks.arbiter_pass(limit=10)
    assert db.query_value("SELECT status FROM users WHERE id = %s", (author["id"],)) == "banned"
    assert _report_status(db, cases[2]) == mod.RESOLVED_BANNED


def test_a_ban_by_the_arbiter_is_recorded_against_the_bot_that_did_it(
    db, make_case, author, reporter, arbiter, monkeypatch
):
    """An automated ban has to be as reviewable as a human one."""
    monkeypatch.setenv("REPEAT_OFFENDER_THRESHOLD", "1")
    _reported_case(db, make_case, author, reporter, BORDERLINE)
    moderation_tasks.work_report_queue()

    moderation_tasks.arbiter_pass()

    trail = mod.history("user", author["id"], conn=db)
    assert trail[0]["action"] == "ban"
    assert trail[0]["actor"]["id"] == arbiter
    assert trail[0]["actor_is_bot"] is True


def test_the_arbiter_dismisses_a_report_whose_content_has_gone(
    db, make_case, author, reporter
):
    """A withdrawn filing between the clerk's claim and the arbiter's pass.

    Left claimed it would sit in the queue forever, since nothing else ever
    looks at it again.
    """
    case_id = _reported_case(db, make_case, author, reporter, BORDERLINE)
    moderation_tasks.work_report_queue()

    db.execute("UPDATE reports SET target_id = 999999 WHERE target_id = %s", (case_id,))
    db.commit()

    assert moderation_tasks.arbiter_pass() == 1
    assert db.query_value("SELECT status FROM reports") == mod.RESOLVED_DISMISSED


def test_the_arbiter_has_nothing_to_do_when_the_clerk_left_nothing(db):
    assert moderation_tasks.arbiter_pass() == 0


# --- the sweeper ------------------------------------------------------------


def _make_sweepable(db, case_id: int) -> None:
    """Old enough to sweep, and never scanned."""
    db.execute(
        "UPDATE cases SET scanned_at = NULL, "
        "created_at = DATE_SUB(UTC_TIMESTAMP(), INTERVAL 10 MINUTE) WHERE id = %s",
        (case_id,),
    )
    db.commit()


def test_the_sweeper_hides_toxic_content_nobody_reported(db, make_case, author):
    """The safety net: not everything abusive gets reported.

    Especially on an old case nobody is reading any more, which is exactly
    where the sweep earns its keep.
    """
    case_id = make_case(author["id"], body=TOXIC)
    _make_sweepable(db, case_id)

    assert moderation_tasks.sweep_unscanned() == 1

    assert _status(db, case_id) == "hidden"


def test_the_sweeper_flags_borderline_content_without_telling_the_author(
    db, make_case, author
):
    """`notify=False`, and marked rather than removed.

    A re-scan of month-old content should not deliver a fresh notification
    about something its author has long since forgotten writing - and flagged
    content is still public, so there is nothing to tell them about.
    """
    case_id = make_case(author["id"], body=BORDERLINE)
    _make_sweepable(db, case_id)

    assert moderation_tasks.sweep_unscanned() == 1

    assert _status(db, case_id) == "flagged"
    assert db.query_value("SELECT COUNT(*) FROM notifications") == 0


def test_content_the_sweeper_judged_fine_is_stamped_and_never_swept_again(
    db, make_case, author
):
    """The bug the `else: mark_scanned` branch exists to prevent.

    `set_content_status` stamps `scanned_at` on its way past, but returns early
    when the status has not changed - so an `ok` verdict would leave the row
    unstamped, back in the next `unscanned()` batch, and re-scanned on every
    sweep forever.
    """
    case_id = make_case(author["id"], body=HARMLESS)
    _make_sweepable(db, case_id)

    assert moderation_tasks.sweep_unscanned() == 1
    assert _status(db, case_id) == "published"
    assert db.query_value("SELECT scanned_at FROM cases WHERE id = %s", (case_id,)) is not None

    assert moderation_tasks.sweep_unscanned() == 0
    assert mod.unscanned(conn=db) == []


def test_the_sweeper_leaves_content_posted_a_moment_ago_alone(db, make_case, author):
    """The age filter, which stops it racing the publish-time scan.

    Without it the sweeper and `create_case` would scan the same words in the
    same second and write two scan rows for one decision.
    """
    case_id = make_case(author["id"], body=TOXIC)
    db.execute("UPDATE cases SET scanned_at = NULL WHERE id = %s", (case_id,))
    db.commit()

    assert moderation_tasks.sweep_unscanned() == 0
    assert _status(db, case_id) == "published"


def test_the_sweeper_reads_comments_as_well_as_filings(
    db, make_case, make_comment, author
):
    """One queue over two tables - abuse is more often in a reply than a filing."""
    case_id = make_case(author["id"])
    comment_id = make_comment(case_id, author["id"], body=TOXIC)
    db.execute(
        "UPDATE comments SET scanned_at = NULL, "
        "created_at = DATE_SUB(UTC_TIMESTAMP(), INTERVAL 10 MINUTE) WHERE id = %s",
        (comment_id,),
    )
    db.execute("UPDATE cases SET scanned_at = UTC_TIMESTAMP() WHERE id = %s", (case_id,))
    db.commit()

    assert moderation_tasks.sweep_unscanned() == 1

    assert db.query_value(
        "SELECT moderation_status FROM comments WHERE id = %s", (comment_id,)
    ) == "hidden"


def test_a_sweep_run_twice_reaches_the_same_place(db, make_case, author):
    """`scanned_at` is the claim, so the second pass finds an empty queue."""
    case_id = make_case(author["id"], body=TOXIC)
    _make_sweepable(db, case_id)

    assert moderation_tasks.sweep_unscanned() == 1
    assert moderation_tasks.sweep_unscanned() == 0

    assert db.query_value(
        "SELECT COUNT(*) FROM moderation_actions WHERE target_id = %s", (case_id,)
    ) == 1


# --- publish-time screening -------------------------------------------------


def test_toxic_content_is_rejected_at_publish_time_but_still_stored(db, author):
    """"Rejected filings are still INSERTED, then reported as rejected."

    They never publish, so "toxic = rejected" holds - and the evidence survives
    for the admin queue rather than being discarded at the door.
    """
    from app.services import cases_service

    result, case_id = cases_service.create_case(
        author["id"], "כותרת רגילה", TOXIC, "הנתבע", conn=db
    )
    db.commit()

    assert result == "rejected"
    assert case_id is not None
    assert _status(db, case_id) == "rejected"
    assert db.query_value("SELECT COUNT(*) FROM moderation_scans WHERE target_id = %s", (case_id,)) == 1


def test_borderline_content_publishes_flagged_rather_than_being_blocked(db, author):
    """One hostile adjective does not silence an author.

    This is the difference the four statuses buy, at the moment it matters
    most - the author is not stopped from filing.
    """
    from app.services import cases_service

    result, case_id = cases_service.create_case(
        author["id"], "כותרת רגילה", BORDERLINE, "הנתבע", conn=db
    )
    db.commit()

    assert result == "ok"
    assert _status(db, case_id) == "flagged"


def test_a_rejected_filing_gets_no_feed_presence_at_all(db, author):
    """No activity row, and nobody auto-followed.

    Following your own rejected filing would put a card on your personal feed
    that nobody else can see and that you cannot do anything about.
    """
    from app.services import cases_service

    _, case_id = cases_service.create_case(
        author["id"], "כותרת רגילה", TOXIC, "הנתבע", conn=db
    )
    db.commit()

    assert db.query_value("SELECT COUNT(*) FROM case_activity WHERE case_id = %s", (case_id,)) == 0
    assert db.query_value("SELECT COUNT(*) FROM case_follows WHERE case_id = %s", (case_id,)) == 0
