# -*- coding: utf-8 -*-
"""The trial state machine, and the promise that running a tick twice is safe.

`trial_service`'s docstring states the shape every transition follows:

    1. claim the row (`FOR UPDATE SKIP LOCKED`, or a UNIQUE index);
    2. do the work;
    3. commit with a **status-guarded UPDATE whose rowcount is checked**.

  ...Combined with `comments.dedupe_key` and `jury_panels.case_id` being a
  primary key, two workers running flat out produce exactly the same final
  state as one.

That is a claim about a database, and it cannot be checked anywhere else. The
guards are `FOR UPDATE SKIP LOCKED`, `INSERT IGNORE` against a primary key, a
UNIQUE index over a nullable column, and a rowcount from a conditional UPDATE -
four MySQL behaviours, none of which a fake can do more than agree with.

So the centrepiece here is `test_a_tick_run_twice_reaches_the_same_state`: run
the whole tick over the same due work twice and compare *everything* - status,
verdict, sentence, comment count, votes, tally - to the same lifecycle run once.
That is the assertion the design exists to satisfy, and it is stronger than
checking any individual guard, because it would catch a new transition added
later without one.

Time is handled by moving `phase_deadline_at` into the past rather than by
waiting. The deadlines are written by the database from its own clock, so the
only honest way to make a phase "due" is to tell the database it is.
"""

from __future__ import annotations

import pytest

from app.services import jury_service, trial_service
from worker import loop, trial_tasks

pytestmark = [pytest.mark.worker, pytest.mark.integration]


@pytest.fixture
def author(make_user):
    return make_user("התובעת", "author@lolsuit.test")


@pytest.fixture
def case(make_case, author):
    return make_case(author["id"])


def _make_due(db, case_id: int) -> None:
    """Tell the database this case's current phase has run out."""
    db.execute(
        "UPDATE cases SET phase_deadline_at = DATE_SUB(UTC_TIMESTAMP(), INTERVAL 1 MINUTE) "
        "WHERE id = %s",
        (case_id,),
    )
    db.commit()


def _jurors_due(db, case_id: int) -> None:
    db.execute(
        "UPDATE jury_panel_members SET speaks_at = DATE_SUB(UTC_TIMESTAMP(), INTERVAL 1 MINUTE) "
        "WHERE case_id = %s",
        (case_id,),
    )
    db.commit()


def _status(db, case_id: int) -> str:
    return db.query_value("SELECT status FROM cases WHERE id = %s", (case_id,))


def _snapshot(db, case_id: int) -> dict:
    """Everything a second run must not change."""
    case = db.query_one(
        "SELECT status, verdict, sentence_text FROM cases WHERE id = %s", (case_id,)
    )
    panel = db.query_one(
        "SELECT judge_user_id, tally_guilty, tally_not_guilty, tiebreak_used "
        "FROM jury_panels WHERE case_id = %s",
        (case_id,),
    )
    return {
        "case": case,
        "panel": panel,
        "comments": db.query_all(
            "SELECT role, dedupe_key, author_id FROM comments WHERE case_id = %s "
            "ORDER BY id",
            (case_id,),
        ),
        "votes": db.query_all(
            "SELECT seat, juror_user_id, vote FROM jury_panel_members "
            "WHERE case_id = %s ORDER BY seat",
            (case_id,),
        ),
    }


def _run_to_verdict(db, case_id: int) -> None:
    """Drive one case all the way through, tick by tick."""
    _make_due(db, case_id)
    trial_tasks.advance_witness_phase()
    _jurors_due(db, case_id)
    trial_tasks.run_due_jurors(limit=20)
    _make_due(db, case_id)
    trial_tasks.advance_verdicts()


# --- the phases, in order ---------------------------------------------------


def test_a_new_filing_opens_straight_into_the_witness_phase(db, case):
    """`create_case` writes 'witness_phase' directly, skipping 'filed'.

    'filed' exists in the ENUM for a hand-inserted row, and `open_filed_cases`
    is the defensive sweep that rescues one - which is why the sweep normally
    finds nothing.
    """
    assert _status(db, case) == "witness_phase"
    assert db.query_value("SELECT phase_deadline_at FROM cases WHERE id = %s", (case,)) is not None

    assert trial_tasks.open_filed_cases() == 0


def test_a_case_stuck_in_filed_is_rescued_and_given_a_deadline(db, case):
    """A row with no deadline would otherwise sit there forever.

    Nothing moves a case whose `phase_deadline_at` is NULL, because every
    `due_cases` query requires one - so without this sweep the case is
    unreachable by the worker at all.
    """
    db.execute(
        "UPDATE cases SET status = 'filed', phase_deadline_at = NULL WHERE id = %s", (case,)
    )
    db.commit()

    assert trial_tasks.open_filed_cases() == 1

    assert _status(db, case) == "witness_phase"
    assert db.query_value("SELECT phase_deadline_at FROM cases WHERE id = %s", (case,)) is not None


def test_a_phase_does_not_advance_before_its_deadline(db, case):
    """`due_cases` requires `phase_deadline_at <= UTC_TIMESTAMP()`.

    Advancing early would collapse the whole calendar into one tick, which is
    what makes this worth asserting separately from the happy path.
    """
    assert trial_tasks.advance_witness_phase() == 0
    assert _status(db, case) == "witness_phase"


def test_the_witness_phase_closes_by_seating_seven_jurors_and_a_judge(db, case):
    """The panel is the phase transition, not a side effect of it.

    `seat_panel` and the status UPDATE are in one transaction, so a case can
    never be in deliberation without a jury - which every later step assumes.
    """
    _make_due(db, case)

    assert trial_tasks.advance_witness_phase() == 1

    assert _status(db, case) == "jury_deliberation"
    panel = jury_service.get_panel(case, conn=db)
    assert panel is not None
    assert panel["judge_user_id"] is not None

    members = jury_service.get_members(case, conn=db)
    assert len(members) == jury_service.PANEL_SIZE
    assert [member["seat"] for member in members] == list(range(jury_service.PANEL_SIZE))
    assert len({member["juror_user_id"] for member in members}) == jury_service.PANEL_SIZE


def test_seat_order_is_speaking_order(db, case):
    """Offsets are sorted before being zipped to seats.

    So the panel reads top-to-bottom in the UI and "who spoke first" is a
    question the seat number answers.
    """
    _make_due(db, case)
    trial_tasks.advance_witness_phase()

    members = jury_service.get_members(case, conn=db)
    speaking_times = [member["speaks_at"] for member in members]

    assert speaking_times == sorted(speaking_times)


def test_nobody_sits_in_judgement_of_a_case_they_are_a_party_to(db, make_user, make_case):
    """Bots sue each other, so a party can be an agent.

    Without the exclusion the defendant could be drawn onto their own jury, or
    preside over their own trial.
    """
    juror = db.query_one(
        "SELECT user_id FROM agents WHERE role = 'juror' AND is_active = 1 LIMIT 1"
    )
    judge = db.query_one(
        "SELECT user_id FROM agents WHERE role = 'judge' AND is_active = 1 LIMIT 1"
    )
    case_id = make_case(juror["user_id"])
    db.execute(
        "UPDATE cases SET defendant_user_id = %s WHERE id = %s", (judge["user_id"], case_id)
    )
    _make_due(db, case_id)

    trial_tasks.advance_witness_phase()

    panel = jury_service.get_panel(case_id, conn=db)
    members = jury_service.get_members(case_id, conn=db)
    assert panel["judge_user_id"] != judge["user_id"]
    assert juror["user_id"] not in {member["juror_user_id"] for member in members}


def test_each_juror_speaks_once_at_the_moment_assigned_at_draw_time(db, case):
    """`speaks_at` is absolute, set when the panel is drawn.

    That is what makes the schedule survive a crash: a worker restarting has no
    state to reconstruct, it just reads which moments have passed.
    """
    _make_due(db, case)
    trial_tasks.advance_witness_phase()

    assert trial_tasks.run_due_jurors(limit=20) == 0

    _jurors_due(db, case)
    assert trial_tasks.run_due_jurors(limit=20) == jury_service.PANEL_SIZE

    members = jury_service.get_members(case, conn=db)
    assert all(member["spoke_at"] is not None for member in members)
    assert all(member["vote"] in ("guilty", "not_guilty") for member in members)
    assert db.query_value(
        "SELECT COUNT(*) FROM comments WHERE case_id = %s AND role = 'jury_deliberation'",
        (case,),
    ) == jury_service.PANEL_SIZE


def test_the_verdict_closes_deliberation_and_records_the_tally(db, case):
    _run_to_verdict(db, case)

    row = db.query_one(
        "SELECT status, verdict, sentence_text, verdict_at FROM cases WHERE id = %s", (case,)
    )
    assert row["status"] == "verdict_reached"
    assert row["verdict"] in ("guilty", "not_guilty")
    assert row["verdict_at"] is not None
    # A sentence is something only a conviction carries. An acquittal has
    # nothing to hand down, so the column stays NULL rather than holding an
    # empty string that the card would then have to special-case anyway.
    if row["verdict"] == "guilty":
        assert row["sentence_text"]
    else:
        assert row["sentence_text"] is None

    panel = jury_service.get_panel(case, conn=db)
    assert panel["tally_guilty"] + panel["tally_not_guilty"] == jury_service.PANEL_SIZE
    assert panel["tallied_at"] is not None

    assert db.query_value(
        "SELECT COUNT(*) FROM comments WHERE case_id = %s AND role = 'verdict'", (case,)
    ) == 1


def test_a_juror_who_never_got_their_moment_still_votes_at_verdict_time(db, case):
    """The catch-up in `advance_to_verdict`.

    A worker down for the whole deliberation window must still produce a
    seven-juror record, or the tally would be taken over whoever happened to
    speak before it died.
    """
    _make_due(db, case)
    trial_tasks.advance_witness_phase()

    # No juror ever speaks: straight from seating to the verdict deadline.
    _make_due(db, case)
    assert trial_tasks.advance_verdicts() == 1

    members = jury_service.get_members(case, conn=db)
    assert all(member["vote"] is not None for member in members)
    panel = jury_service.get_panel(case, conn=db)
    assert panel["tally_guilty"] + panel["tally_not_guilty"] == jury_service.PANEL_SIZE


def test_the_case_is_retired_a_day_after_the_verdict(db, case):
    """Closing ends the trial, not the conversation.

    Likes and comments stay open forever - `close_case` touches neither.
    """
    _run_to_verdict(db, case)
    _make_due(db, case)

    assert trial_tasks.close_cases() == 1

    row = db.query_one(
        "SELECT status, closed_at, phase_deadline_at, verdict FROM cases WHERE id = %s", (case,)
    )
    assert row["status"] == "closed"
    assert row["closed_at"] is not None
    # Nothing is due any more, so the worker stops looking at it.
    assert row["phase_deadline_at"] is None
    assert row["verdict"] is not None


def test_the_author_and_the_defendant_are_told_the_verdict(db, author, make_user, make_case):
    """A verdict on a case you are a party to is the one notification that
    cannot be missed."""
    defendant = make_user("הנתבע", "defendant@lolsuit.test")
    case_id = make_case(author["id"])
    db.execute("UPDATE cases SET defendant_user_id = %s WHERE id = %s", (defendant["id"], case_id))
    db.commit()

    _run_to_verdict(db, case_id)

    for user_id in (author["id"], defendant["id"]):
        assert db.query_value(
            "SELECT COUNT(*) FROM notifications WHERE user_id = %s AND type = 'verdict'",
            (user_id,),
        ) == 1


# --- idempotency ------------------------------------------------------------


def test_a_tick_run_twice_reaches_the_same_state_as_running_it_once(db, case):
    """The claim the whole design exists to support, checked end to end.

    One case, driven all the way to closed, snapshotted - and then every task
    in the lifecycle run a second time over the same rows. The snapshot must
    come back byte for byte identical: same status, same verdict, same
    sentence, same panel, same votes, same tally, and above all the same
    comments, in the same order, with the same dedupe keys.

    It is one case rather than two on purpose. The jury draw is seeded on
    `case_id`, deliberately, so that a panel is reproducible - which means two
    different cases get two different juries and two legitimately different
    verdicts. Comparing them would be comparing the seed, not the guards.

    This is stronger than asserting any individual guard, because it would also
    catch a transition added later that forgot to have one.
    """
    _run_to_verdict(db, case)
    _make_due(db, case)
    trial_tasks.close_cases()

    before = _snapshot(db, case)
    assert before["case"]["status"] == "closed"
    assert len(before["comments"]) == jury_service.PANEL_SIZE + 1
    assert len(before["votes"]) == jury_service.PANEL_SIZE

    # Everything again, in the same order, over rows that are already finished.
    for _ in range(2):
        _jurors_due(db, case)
        trial_tasks.advance_witness_phase()
        trial_tasks.run_due_jurors(limit=40)
        trial_tasks.advance_verdicts()
        trial_tasks.close_cases()
        trial_tasks.open_filed_cases()

    assert _snapshot(db, case) == before


def test_replaying_a_whole_tick_over_finished_work_changes_nothing(db, case):
    """The same property through `loop.tick()` rather than the tasks directly.

    A guard that lived in `trial_tasks` rather than in the service would pass
    the test above and still let a second *tick* duplicate work, because the
    tick is the thing that actually runs twice in production.
    """
    _make_due(db, case)
    loop.tick()
    _jurors_due(db, case)
    loop.tick()
    _make_due(db, case)
    loop.tick()
    _make_due(db, case)
    loop.tick()

    before = _snapshot(db, case)
    assert before["case"]["status"] == "closed"

    for _ in range(3):
        loop.tick()

    assert _snapshot(db, case) == before


def test_seating_a_panel_twice_is_stopped_by_the_primary_key(db, case):
    """`jury_panels.case_id` IS the primary key, so idempotency is structural.

    `INSERT IGNORE` returning rowcount 0 is the whole check - there is no
    "does a panel exist" query anywhere, and so no window between asking and
    inserting.
    """
    _make_due(db, case)
    trial_tasks.advance_witness_phase()

    draw = jury_service.select_panel(
        case_id=case,
        juror_ids=list(range(1000, 1020)),
        judge_ids=[2000],
        filed_at=db.query_value("SELECT filed_at FROM cases WHERE id = %s", (case,)),
        window_start_minutes=0,
        window_end_minutes=10,
    )

    assert jury_service.seat_panel(case, draw, conn=db) == "already_done"
    db.commit()

    assert db.query_value("SELECT COUNT(*) FROM jury_panel_members WHERE case_id = %s", (case,)) == 7


def test_a_juror_cannot_speak_twice_even_if_asked_to(db, case):
    """Two independent guards, and this exercises the second one directly.

    `comments.dedupe_key` makes a duplicate comment physically impossible;
    `record_speech`'s `spoke_at IS NULL` makes a duplicate vote impossible.
    Neither leans on the other, so a crash between the two is still safe.
    """
    _make_due(db, case)
    trial_tasks.advance_witness_phase()
    _jurors_due(db, case)

    member = jury_service.due_jurors(1, conn=db)[0]
    assert trial_service.speak_as_juror(member, conn=db) == "ok"
    db.commit()

    assert trial_service.speak_as_juror(member, conn=db) == "already_done"
    db.commit()

    assert db.query_value(
        "SELECT COUNT(*) FROM comments WHERE dedupe_key = %s", (f"jury:{member['id']}",)
    ) == 1
    assert jury_service.record_speech(member["id"], "guilty", None, conn=db) == "already_done"


def test_every_transition_refuses_to_run_from_the_wrong_status(db, case):
    """The status guard, asked directly rather than through a tick.

    Each of these is the second worker's experience: it finds the status
    already changed, its UPDATE matches nothing, and it abandons the
    transaction.
    """
    assert trial_service.advance_to_verdict(case, conn=db) == "already_done"
    assert trial_service.close_case(case, conn=db) == "already_done"

    _make_due(db, case)
    trial_tasks.advance_witness_phase()

    assert trial_service.advance_to_deliberation(case, conn=db) == "already_done"
    assert trial_service.close_case(case, conn=db) == "already_done"


def test_a_transition_on_a_case_that_is_gone_is_not_found(db):
    assert trial_service.advance_to_deliberation(999_999, conn=db) == "not_found"
    assert trial_service.advance_to_verdict(999_999, conn=db) == "not_found"
    assert trial_service.close_case(999_999, conn=db) == "already_done"


def test_a_case_cannot_be_seated_when_the_agent_pools_are_too_small(db, case, monkeypatch):
    """"no_pool", and the case stays put so seeding fixes it unattended.

    Raising here would abort the whole tick over a configuration problem that
    resolves itself the moment `app.seed` runs.
    """
    from app.services import agents_service

    monkeypatch.setattr(agents_service, "pool_ids", lambda *a, **k: [])
    _make_due(db, case)

    assert trial_service.advance_to_deliberation(case, conn=db) == "no_pool"
    assert _status(db, case) == "witness_phase"
    assert jury_service.get_panel(case, conn=db) is None


# --- the tick itself --------------------------------------------------------


def test_a_tick_counts_itself_and_stamps_when_it_ran(db):
    """`worker_state` is durable so "every fourth tick" survives a restart.

    Kept in the database rather than in memory, which is also what lets
    /api/health report it.
    """
    assert db.query_value("SELECT tick_count FROM worker_state WHERE name = 'scheduler'") == 0

    summary = loop.tick()

    assert summary["tick"] == 1
    assert db.query_value("SELECT tick_count FROM worker_state WHERE name = 'scheduler'") == 1
    assert db.query_value("SELECT last_tick_at FROM worker_state WHERE name = 'scheduler'") is not None

    assert loop.tick()["tick"] == 2


def test_a_whole_tick_advances_a_due_case(db, case):
    """The wiring, rather than the individual tasks.

    A task that was written but never added to `tick()` would pass every test
    above and do nothing in production.
    """
    _make_due(db, case)

    summary = loop.tick()

    assert summary["juries_seated"] == 1
    assert _status(db, case) == "jury_deliberation"


def test_one_failing_task_does_not_abort_the_rest_of_the_tick(db, case, monkeypatch):
    """`safe()` logs and swallows, and that is a deliberate choice.

    The case that cannot advance must not stop six others from closing - so a
    task raising has to cost its own result and nothing else.
    """
    def explode(*args, **kwargs):
        raise RuntimeError("the court is on fire")

    monkeypatch.setattr(trial_tasks, "close_cases", explode)
    _make_due(db, case)

    summary = loop.tick()

    assert summary["closed"] == 0
    assert summary["juries_seated"] == 1
    assert _status(db, case) == "jury_deliberation"


def test_periodic_tasks_run_on_their_own_interval_and_not_every_tick(db, monkeypatch):
    """Read from configuration at tick time, so it changes without a restart.

    The sweep is not free - it re-scans published content - and running it
    fifteen times a minute would make the moderation lexicon the busiest thing
    in the application.
    """
    monkeypatch.setenv("SWEEP_EVERY_TICKS", "3")
    swept: list[int] = []
    monkeypatch.setattr(
        "worker.moderation_tasks.sweep_unscanned", lambda *a, **k: swept.append(1) or 0
    )

    for _ in range(6):
        loop.tick()

    # Ticks 3 and 6 of six.
    assert len(swept) == 2


def test_a_task_interval_of_zero_switches_it_off_rather_than_dividing_by_zero(db, monkeypatch):
    monkeypatch.setenv("SOCIAL_EVERY_TICKS", "0")

    summary = loop.tick()

    assert summary["bot_actions"] == 0


def test_the_advisory_lock_lets_exactly_one_worker_tick(db):
    """`GET_LOCK` with a zero timeout: never queue, just skip this tick.

    MySQL releases a named lock when the holding connection dies, so a `kill
    -9` needs no cleanup - no `locked_until` column and no reaper.
    """
    from app.db import connect

    first = connect()
    second = connect()
    try:
        assert loop.acquire_lock(first) is True
        assert loop.acquire_lock(second) is False

        loop.release_lock(first)
        assert loop.acquire_lock(second) is True
        loop.release_lock(second)
    finally:
        first.close()
        second.close()


# --- housekeeping -----------------------------------------------------------


def test_housekeeping_removes_only_rows_nothing_can_ever_read_again(db, author):
    """Nothing here is load-bearing, which is why it can run rarely.

    `resolve_session` already refuses an expired session and
    `consume_password_reset` already refuses a spent token; this only stops two
    append-only tables from growing forever.
    """
    from app.services import auth_service
    from worker import housekeeping_tasks

    live = auth_service.create_session(author["id"], ttl_days=7, conn=db)
    auth_service.create_session(author["id"], ttl_days=7, conn=db)
    auth_service.create_password_reset(author["id"], ttl_minutes=30, conn=db)
    db.commit()

    db.execute(
        "UPDATE sessions SET expires_at = DATE_SUB(UTC_TIMESTAMP(), INTERVAL 1 DAY) "
        "WHERE token_hash <> %s",
        (auth_service.hash_token(live),),
    )
    db.execute(
        "UPDATE password_resets SET expires_at = DATE_SUB(UTC_TIMESTAMP(), INTERVAL 3 DAY)"
    )
    db.commit()

    assert housekeeping_tasks.purge_stale_auth_rows() == 2

    assert db.query_value("SELECT COUNT(*) FROM sessions") == 1
    assert db.query_value("SELECT COUNT(*) FROM password_resets") == 0
    assert auth_service.resolve_session(live, conn=db) is not None


def test_a_spent_reset_token_is_kept_for_a_day_before_being_purged(db, author):
    """So "did that link ever get used?" is still answerable afterwards."""
    from app.services import auth_service

    raw = auth_service.create_password_reset(author["id"], ttl_minutes=30, conn=db)
    db.commit()
    auth_service.consume_password_reset(raw, conn=db)
    db.commit()

    assert auth_service.purge_spent_password_resets(conn=db) == 0
    db.commit()

    db.execute("UPDATE password_resets SET used_at = DATE_SUB(UTC_TIMESTAMP(), INTERVAL 2 DAY)")
    db.commit()

    assert auth_service.purge_spent_password_resets(conn=db) == 1
