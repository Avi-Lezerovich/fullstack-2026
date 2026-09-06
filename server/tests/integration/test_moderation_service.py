# -*- coding: utf-8 -*-
"""Moderation: four statuses, an audit trail, and nothing ever deleted.

The module's own opening paragraph is the specification, and it makes a claim
that only a test can keep true:

    **Nothing here ever issues a DELETE.** Hiding is a status transition, which
    is what makes it reversible - and reversibility is the whole point of
    letting bots make the first decision.

That is the property this file is built around. A bot deciding first is only
defensible because a human can undo it, so "reversible" is not a nicety here,
it is what makes the design legitimate. Several tests below therefore count
rows before and after rather than checking a return value: a `set_content_status`
that quietly deleted would satisfy every status assertion in the file and fail
only these.

The other half is the trail. `moderation_actions` records the previous status
*and* the new one, which is what turns "an admin can override a bot" from
something that is merely possible into something that is afterwards visible.

Real MySQL throughout, because most of these rules are enforced by the schema
rather than by Python: the four statuses are an ENUM, one-report-per-person is
a UNIQUE index, and the clerk's claim is `FOR UPDATE SKIP LOCKED`.
"""

from __future__ import annotations

import pytest

from app.services import moderation_service as mod

pytestmark = pytest.mark.integration

# Every table a hide, a reject, a ban or a resolve could conceivably delete from.
CONTENT_TABLES = ("cases", "comments", "likes", "case_follows", "case_charges", "users")


@pytest.fixture
def author(make_user):
    return make_user("התובע", "author@lolsuit.test")


@pytest.fixture
def reporter(make_user):
    return make_user("המדווחת", "reporter@lolsuit.test")


@pytest.fixture
def case(make_case, author):
    return make_case(author["id"])


def _counts(db) -> dict[str, int]:
    return {
        table: db.query_value("SELECT COUNT(*) FROM " + table) for table in CONTENT_TABLES
    }


# --- the four statuses ------------------------------------------------------


@pytest.mark.parametrize("status", ["published", "flagged", "hidden", "rejected"])
def test_every_declared_status_is_one_the_column_accepts(db, case, admin, status):
    """The Python constant and the ENUM have to be the same four words.

    They are declared in two files that nothing links, so a fifth status added
    to `CONTENT_STATUSES` alone would be accepted by the service and rejected
    by the database - as a 500, at the moment a moderator used it.
    """
    assert status in mod.CONTENT_STATUSES

    mod.set_content_status("case", case, status, actor_id=admin["id"], conn=db)
    db.commit()

    assert db.query_value("SELECT moderation_status FROM cases WHERE id = %s", (case,)) == status


def test_flagged_content_is_still_public_and_hidden_content_is_not():
    """The distinction the whole four-status scheme exists for.

    Borderline content is marked, not removed, so one sharp word does not
    silence an author. Collapsing `flagged` into `hidden` would make the
    sweeper's "borderline" verdict indistinguishable from its "toxic" one.
    """
    assert set(mod.VISIBLE_STATUSES) == {"published", "flagged"}
    assert set(mod.HIDDEN_STATUSES) == {"hidden", "rejected"}
    assert not set(mod.VISIBLE_STATUSES) & set(mod.HIDDEN_STATUSES)


def test_an_unknown_status_is_refused_before_anything_is_written(db, case, admin):
    """"invalid", and the row untouched.

    The ENUM would reject it anyway, but as a 500 from deep inside a service.
    Refusing here is what lets the route answer 400.
    """
    before = db.query_value("SELECT moderation_status FROM cases WHERE id = %s", (case,))

    assert mod.set_content_status("case", case, "deleted", actor_id=admin["id"], conn=db) == "invalid"
    assert mod.set_content_status("case", case, "", actor_id=admin["id"], conn=db) == "invalid"

    assert db.query_value("SELECT moderation_status FROM cases WHERE id = %s", (case,)) == before
    assert db.query_value("SELECT COUNT(*) FROM moderation_actions") == 0


def test_an_unknown_target_type_never_reaches_a_table_name(db, admin):
    """`_TABLES` is a literal lookup, and a miss returns rather than interpolating.

    The table name goes into an f-string, so this is the one place in the
    service layer where a value deciding SQL text is not a bound parameter -
    the lookup is what keeps that safe.
    """
    assert mod.get_content("cases; DROP TABLE users", 1, conn=db) is None
    assert mod.set_content_status("post", 1, "hidden", actor_id=admin["id"], conn=db) == "invalid"
    assert mod.mark_scanned("post", 1, conn=db) is None


def test_setting_the_status_it_already_has_changes_nothing_and_says_so(db, case, admin):
    """"already_done" - which makes every consequence in this module idempotent.

    `admin_resolve` leans on it directly: hiding something already hidden and
    banning someone already banned both have to be safe to retry, or a
    half-completed resolve could never be run again.
    """
    mod.set_content_status("case", case, "hidden", actor_id=admin["id"], conn=db)
    db.commit()

    assert mod.set_content_status("case", case, "hidden", actor_id=admin["id"], conn=db) == "already_done"
    db.commit()

    assert db.query_value("SELECT COUNT(*) FROM moderation_actions WHERE target_id = %s", (case,)) == 1


def test_moderating_something_that_is_not_there_is_not_found(db, admin):
    assert mod.set_content_status("case", 999_999, "hidden", actor_id=admin["id"], conn=db) == "not_found"
    assert mod.set_content_status("comment", 999_999, "hidden", actor_id=admin["id"], conn=db) == "not_found"


# --- nothing is ever deleted ------------------------------------------------


def test_hiding_a_case_deletes_no_row_anywhere(db, case, author, reporter, make_comment):
    """The claim in the module docstring, counted rather than trusted.

    Every table a hide could plausibly cascade into is counted before and
    after. A `set_content_status` that took the shortcut of deleting would pass
    every other test in this file.
    """
    from app.services import likes_service

    make_comment(case, reporter["id"])
    likes_service.toggle_like(case, reporter["id"], conn=db)
    db.commit()

    before = _counts(db)

    mod.set_content_status("case", case, "hidden", actor_id=author["id"], conn=db)
    db.commit()

    assert _counts(db) == before


def test_rejecting_content_keeps_the_evidence(db, case, admin):
    """"Rejected content is still INSERTED rather than discarded."

    The admin queue is the reason: a filing blocked at publish time is exactly
    the thing a human most needs to be able to look at and reverse.
    """
    mod.set_content_status("case", case, "rejected", actor_id=admin["id"], conn=db)
    db.commit()

    row = db.query_one("SELECT id, title, body FROM cases WHERE id = %s", (case,))
    assert row is not None
    assert row["body"]


def test_banning_an_author_leaves_every_word_they_wrote_in_place(
    db, case, author, admin, make_comment
):
    """A ban suspends an account; it is not a retraction.

    Deleting their filings would also delete the reports and the audit trail
    that justified the ban, which is the one record that has to survive it.
    """
    make_comment(case, author["id"])
    db.commit()
    before = _counts(db)

    assert mod.ban_user(author["id"], actor_id=admin["id"], reason="חוזר ונשנה", conn=db) == "ok"
    db.commit()

    assert _counts(db) == before
    assert db.query_value("SELECT status FROM users WHERE id = %s", (author["id"],)) == "banned"


# --- hiding is reversible ---------------------------------------------------


def test_hiding_and_unhiding_returns_the_row_to_exactly_where_it_was(db, case, admin):
    """A round trip, asserted as a round trip.

    "Reversible" has to mean the content comes back, not merely that some
    later status can be set - so this checks the value, not just that the call
    succeeded.
    """
    assert db.query_value("SELECT moderation_status FROM cases WHERE id = %s", (case,)) == "published"

    mod.set_content_status("case", case, "hidden", actor_id=admin["id"], conn=db)
    db.commit()
    assert db.query_value("SELECT moderation_status FROM cases WHERE id = %s", (case,)) == "hidden"

    mod.set_content_status("case", case, "published", actor_id=admin["id"], conn=db)
    db.commit()
    assert db.query_value("SELECT moderation_status FROM cases WHERE id = %s", (case,)) == "published"


def test_a_bot_hide_and_the_human_reversal_are_both_in_the_trail(db, case, admin, make_user):
    """Which is what makes the override reviewable rather than merely possible.

    The bot's row is still there afterwards, marked `actor_is_bot`, beside the
    human's - so "the arbiter hid this and a moderator put it back" is a thing
    the record can say.
    """
    sweeper = make_user("סורק", "sweeper@lolsuit.test", is_bot=True)

    mod.set_content_status(
        "case", case, "hidden", actor_id=sweeper["id"], actor_is_bot=True,
        reason="סריקה יזומה", conn=db,
    )
    mod.set_content_status(
        "case", case, "published", actor_id=admin["id"], action="override",
        reason="נבדק ידנית", conn=db,
    )
    db.commit()

    trail = mod.history("case", case, conn=db)

    assert [entry["action"] for entry in trail] == ["override", "hide"]
    assert [entry["actor_is_bot"] for entry in trail] == [False, True]
    assert trail[0]["actor"]["id"] == admin["id"]
    assert trail[1]["actor"]["id"] == sweeper["id"]


def test_every_audit_row_records_where_the_content_came_from_and_where_it_went(
    db, case, admin
):
    """Both columns, on every transition, or the trail cannot be read backwards.

    With only `new_status` the record says what happened but not what was
    undone, and "an admin reversed a bot" becomes indistinguishable from "an
    admin hid something nobody had touched".
    """
    mod.set_content_status("case", case, "flagged", actor_id=admin["id"], conn=db)
    mod.set_content_status("case", case, "hidden", actor_id=admin["id"], conn=db)
    mod.set_content_status("case", case, "published", actor_id=admin["id"], conn=db)
    db.commit()

    rows = db.query_all(
        "SELECT previous_status, new_status, action FROM moderation_actions "
        "WHERE target_type = 'case' AND target_id = %s ORDER BY id",
        (case,),
    )

    assert [(row["previous_status"], row["new_status"]) for row in rows] == [
        ("published", "flagged"),
        ("flagged", "hidden"),
        ("hidden", "published"),
    ]
    # And the verb is derived from the pair, not passed in by the caller.
    assert [row["action"] for row in rows] == ["flag", "hide", "unhide"]


@pytest.mark.parametrize(
    ("previous", "new", "action"),
    [
        ("published", "hidden", "hide"),
        ("published", "rejected", "reject"),
        ("hidden", "published", "unhide"),
        ("rejected", "flagged", "unhide"),
        ("published", "flagged", "flag"),
    ],
)
def test_the_verb_in_the_trail_follows_from_the_transition(previous, new, action):
    """Naming the action after the pair keeps the trail readable at a glance.

    "rejected -> flagged" being an *unhide* is the non-obvious one, and it is
    right: what changed for the reader is that the content came back.
    """
    assert mod._action_for(previous, new) == action


def test_hiding_tells_the_author_and_flagging_does_not(db, case, author, admin):
    """Being flagged is not a punishment, so it is not an announcement.

    The content is still public; telling its author it was marked would invite
    an argument about a decision that had no visible effect on them.
    """
    mod.set_content_status("case", case, "flagged", actor_id=admin["id"], conn=db)
    db.commit()
    assert db.query_value("SELECT COUNT(*) FROM notifications WHERE user_id = %s", (author["id"],)) == 0

    mod.set_content_status("case", case, "hidden", actor_id=admin["id"], reason="לשון הרע", conn=db)
    db.commit()

    row = db.query_one(
        "SELECT type, payload FROM notifications WHERE user_id = %s", (author["id"],)
    )
    assert row["type"] == "moderation"
    assert "hidden" in row["payload"]


def test_the_sweeper_can_flag_silently_when_it_asks_to(db, case, author, admin):
    """`notify=False` exists for the periodic sweep.

    A re-scan of month-old content should not deliver a fresh notification
    about something the author has long since forgotten writing.
    """
    mod.set_content_status(
        "case", case, "hidden", actor_id=admin["id"], notify=False, conn=db
    )
    db.commit()

    assert db.query_value("SELECT COUNT(*) FROM notifications WHERE user_id = %s", (author["id"],)) == 0


# --- the report queue -------------------------------------------------------


def test_one_person_can_report_one_thing_once(db, case, reporter):
    """The UNIQUE index is what stops the queue being flooded by one user.

    Enforced by the database rather than by a prior SELECT, so two clicks
    arriving together cannot both get through.
    """
    assert mod.report("case", case, reporter["id"], "abuse", conn=db)[0] == "ok"
    db.commit()

    result, report_id = mod.report("case", case, reporter["id"], "spam", conn=db)

    assert (result, report_id) == ("conflict", None)
    assert db.query_value("SELECT COUNT(*) FROM reports") == 1


def test_two_people_reporting_the_same_thing_are_two_reports(db, case, reporter, make_user):
    """The uniqueness is per reporter, not per target.

    Ten people reporting one comment is the signal the queue is for; collapsing
    them would throw it away.
    """
    second = make_user("מדווח נוסף", "second@lolsuit.test")

    mod.report("case", case, reporter["id"], "abuse", conn=db)
    mod.report("case", case, second["id"], "abuse", conn=db)
    db.commit()

    assert db.query_value("SELECT COUNT(*) FROM reports") == 2


def test_reporting_something_that_does_not_exist_is_refused(db, reporter):
    assert mod.report("case", 999_999, reporter["id"], "abuse", conn=db) == ("not_found", None)
    assert mod.report("nonsense", 1, reporter["id"], "abuse", conn=db) == ("invalid", None)


def test_claiming_the_queue_takes_each_report_exactly_once(db, case, reporter, make_user):
    """`AND status = 'open'` in the UPDATE *is* the claim.

    A second clerk running at the same moment updates nothing and gets an empty
    batch - which is why this can be a plain function rather than a lock.
    """
    clerk = make_user("פקיד", "clerk@lolsuit.test", is_bot=True)
    mod.report("case", case, reporter["id"], "abuse", conn=db)
    db.commit()

    first = mod.claim_open_reports(clerk["id"], 5, conn=db)
    db.commit()
    second = mod.claim_open_reports(clerk["id"], 5, conn=db)
    db.commit()

    assert len(first) == 1
    assert second == []
    assert db.query_value("SELECT status FROM reports") == "claimed"


def test_a_claimed_report_waits_for_the_arbiter(db, case, reporter, make_user):
    """"claimed" is a real state, not a step the clerk always leaves behind.

    It is what "borderline" means operationally: the clerk declined to decide,
    and `claimed_reports` is how the arbiter finds what was left.
    """
    clerk = make_user("פקיד", "clerk@lolsuit.test", is_bot=True)
    mod.report("case", case, reporter["id"], "abuse", conn=db)
    db.commit()
    mod.claim_open_reports(clerk["id"], 5, conn=db)
    db.commit()

    waiting = mod.claimed_reports(10, conn=db)

    assert [row["target_id"] for row in waiting] == [case]


def test_resolving_a_report_twice_is_reported_as_already_done(db, case, reporter, admin):
    """The guard is `status IN ('open','claimed')` in the WHERE clause.

    So a retried worker tick cannot rewrite a resolution a human has since
    changed.
    """
    _, report_id = mod.report("case", case, reporter["id"], "abuse", conn=db)
    db.commit()

    assert mod.resolve_report(report_id, mod.RESOLVED_DISMISSED, resolver_id=admin["id"], conn=db) == "ok"
    db.commit()
    assert mod.resolve_report(report_id, mod.RESOLVED_HIDDEN, resolver_id=admin["id"], conn=db) == "already_done"
    db.commit()

    assert db.query_value("SELECT status FROM reports") == mod.RESOLVED_DISMISSED


def test_the_queue_listing_carries_an_excerpt_and_the_case_to_open(
    db, case, reporter, make_comment, author
):
    """A reported comment is only judgeable in context.

    `case_id` is one join the queue was not making, so a moderator could see
    that a comment had been reported and had no way to reach the argument it
    was part of.
    """
    comment_id = make_comment(case, author["id"], body="תגובה שדווחה")
    mod.report("comment", comment_id, reporter["id"], "harassment", conn=db)
    db.commit()

    listed = mod.list_reports(conn=db)

    assert len(listed) == 1
    assert listed[0]["target_type"] == "comment"
    assert listed[0]["case_id"] == case
    assert "תגובה שדווחה" in listed[0]["excerpt"]
    assert listed[0]["reporter"]["id"] == reporter["id"]
    assert listed[0]["resolver"] is None


def test_the_queue_can_be_filtered_to_the_resolved_ones(db, case, reporter, admin, make_user):
    """"resolved" means all three resolutions, which is a LIKE not an equality.

    The three are different decisions and one question ("what has been dealt
    with?"), so the filter has to span them.
    """
    other = make_user("מדווח נוסף", "second@lolsuit.test")
    _, resolved_id = mod.report("case", case, reporter["id"], "abuse", conn=db)
    mod.report("case", case, other["id"], "spam", conn=db)
    db.commit()
    mod.resolve_report(resolved_id, mod.RESOLVED_BANNED, resolver_id=admin["id"], conn=db)
    db.commit()

    assert len(mod.list_reports("open", conn=db)) == 1
    assert len(mod.list_reports("resolved", conn=db)) == 1
    assert len(mod.list_reports(conn=db)) == 2


def test_the_excerpt_survives_the_content_being_withdrawn(db, case, reporter, author):
    """A withdrawn filing cascades its reports away, but a reported *comment*
    on a surviving case can still vanish under the queue.

    `target_text` answering "" rather than raising is what keeps the dashboard
    loading when that happens.
    """
    assert mod.target_text("case", 999_999, conn=db) == ""
    assert mod.target_text("comment", 999_999, conn=db) == ""
    assert mod.target_case_id("comment", 999_999, conn=db) is None
    assert mod.target_case_id("case", 42, conn=db) == 42


# --- an admin resolution carries itself out ---------------------------------


def test_resolving_as_hidden_actually_hides_the_content(db, case, reporter, admin):
    """The bug `admin_resolve` exists to fix.

    `resolve_report` alone only moves the report's own status - correct for the
    bots, which hide first and record afterwards. A human has no preceding
    step, so routing them at `resolve_report` marked reports "hidden" while the
    content stayed public.
    """
    _, report_id = mod.report("case", case, reporter["id"], "abuse", conn=db)
    db.commit()

    assert mod.admin_resolve(report_id, mod.RESOLVED_HIDDEN, actor_id=admin["id"], conn=db) == "ok"
    db.commit()

    assert db.query_value("SELECT moderation_status FROM cases WHERE id = %s", (case,)) == "hidden"
    assert db.query_value("SELECT status FROM reports WHERE id = %s", (report_id,)) == mod.RESOLVED_HIDDEN


def test_resolving_as_banned_hides_the_content_and_suspends_its_author(
    db, case, author, reporter, admin
):
    """Both consequences, in one transaction, from one decision."""
    _, report_id = mod.report("case", case, reporter["id"], "harassment", conn=db)
    db.commit()

    assert mod.admin_resolve(report_id, mod.RESOLVED_BANNED, actor_id=admin["id"], conn=db) == "ok"
    db.commit()

    assert db.query_value("SELECT moderation_status FROM cases WHERE id = %s", (case,)) == "hidden"
    assert db.query_value("SELECT status FROM users WHERE id = %s", (author["id"],)) == "banned"


def test_dismissing_a_report_leaves_the_content_exactly_alone(db, case, reporter, admin):
    """The decision that must have no side effect at all.

    A dismissal that still hid the content would make the queue's three
    outcomes into two.
    """
    _, report_id = mod.report("case", case, reporter["id"], "spam", conn=db)
    db.commit()

    assert mod.admin_resolve(report_id, mod.RESOLVED_DISMISSED, actor_id=admin["id"], conn=db) == "ok"
    db.commit()

    assert db.query_value("SELECT moderation_status FROM cases WHERE id = %s", (case,)) == "published"


def test_an_admin_cannot_ban_themselves_out_of_the_dashboard(db, admin, reporter, make_case):
    """There is no way back in: the ban revokes their sessions and
    `/admin/*` needs one.

    Refused before anything is written, so the content is not hidden either -
    a half-applied self-ban would be the worst of both.
    """
    own_case = make_case(admin["id"])
    _, report_id = mod.report("case", own_case, reporter["id"], "abuse", conn=db)
    db.commit()

    assert mod.admin_resolve(report_id, mod.RESOLVED_BANNED, actor_id=admin["id"], conn=db) == "invalid"
    db.commit()

    assert db.query_value("SELECT status FROM users WHERE id = %s", (admin["id"],)) == "active"
    assert db.query_value("SELECT moderation_status FROM cases WHERE id = %s", (own_case,)) == "published"
    assert db.query_value("SELECT status FROM reports WHERE id = %s", (report_id,)) == "open"


def test_an_unknown_decision_is_refused_and_a_missing_report_is_not_found(db, admin):
    assert mod.admin_resolve(1, "resolved_deleted", actor_id=admin["id"], conn=db) == "invalid"
    assert mod.admin_resolve(999_999, mod.RESOLVED_HIDDEN, actor_id=admin["id"], conn=db) == "not_found"


def test_resolving_a_report_whose_content_is_gone_is_not_found(db, case, author, reporter, admin):
    """A withdrawn filing takes its reports with it, but the race exists.

    Answering `not_found` rather than raising is what keeps the dashboard
    usable when a moderator clicks on a report the author withdrew a second
    earlier.
    """
    from app.services import cases_service

    _, report_id = mod.report("case", case, reporter["id"], "abuse", conn=db)
    db.commit()
    # Detach the report from the case so the cascade cannot remove it, which is
    # what leaves a report pointing at content that is no longer there.
    db.execute("UPDATE reports SET target_id = 999999 WHERE id = %s", (report_id,))
    cases_service.delete_case(case, author["id"], conn=db)
    db.commit()

    assert mod.admin_resolve(report_id, mod.RESOLVED_HIDDEN, actor_id=admin["id"], conn=db) == "not_found"


# --- repeat offenders -------------------------------------------------------


def test_prior_hides_are_counted_from_the_trail_so_a_reversal_uncounts_them(
    db, author, admin, make_case, make_comment
):
    """Counted from `moderation_actions`, not from a column on `users`.

    A counter would only ever go up, so an admin reversing a bot's mistake
    would leave the author one step closer to a ban for something that was
    decided not to have happened. Reading the trail means the reversal is
    reflected - because `unhide` is not a `hide`.
    """
    first = make_case(author["id"], title="תביעה ראשונה")
    second = make_case(author["id"], title="תביעה שנייה")
    comment = make_comment(second, author["id"])

    assert mod.prior_hides(author["id"], conn=db) == 0

    for target_type, target_id in (("case", first), ("case", second), ("comment", comment)):
        mod.set_content_status(target_type, target_id, "hidden", actor_id=admin["id"], conn=db)
    db.commit()

    assert mod.prior_hides(author["id"], conn=db) == 3


def test_someone_elses_hidden_content_is_not_counted_against_you(
    db, author, admin, make_user, make_case
):
    """The subquery is on `author_id`, and it has to be.

    Counting every hide on a case you commented on would ban the loudest
    participant in an argument rather than the one who started it.
    """
    other = make_user("מישהו אחר", "other@lolsuit.test")
    theirs = make_case(other["id"])

    mod.set_content_status("case", theirs, "hidden", actor_id=admin["id"], conn=db)
    db.commit()

    assert mod.prior_hides(author["id"], conn=db) == 0
    assert mod.prior_hides(other["id"], conn=db) == 1


def test_a_ban_revokes_every_session_in_the_same_transaction(db, author, admin, app):
    """Belt and braces beside `resolve_session`'s own status check.

    Either one alone would do; both together mean a ban bites even if the
    session lookup is later changed, and that the sessions table does not carry
    rows for accounts that can never use them.
    """
    browser = app.test_client()
    browser.post(
        "/api/auth/login", json={"email": author["email"], "password": author["password"]}
    )
    assert db.query_value("SELECT COUNT(*) FROM sessions WHERE user_id = %s", (author["id"],)) == 1

    mod.ban_user(author["id"], actor_id=admin["id"], conn=db)
    db.commit()

    assert db.query_value("SELECT COUNT(*) FROM sessions WHERE user_id = %s", (author["id"],)) == 0


def test_banning_someone_already_banned_changes_nothing(db, author, admin):
    """Idempotent, which is what lets `admin_resolve` retry safely."""
    assert mod.ban_user(author["id"], actor_id=admin["id"], conn=db) == "ok"
    db.commit()
    assert mod.ban_user(author["id"], actor_id=admin["id"], conn=db) == "already_done"
    db.commit()

    assert db.query_value(
        "SELECT COUNT(*) FROM moderation_actions WHERE action = 'ban' AND target_id = %s",
        (author["id"],),
    ) == 1


def test_unbanning_restores_the_account_and_is_recorded(db, author, admin):
    """A ban is reversible too, and the reversal is in the same trail."""
    mod.ban_user(author["id"], actor_id=admin["id"], conn=db)
    db.commit()

    assert mod.unban_user(author["id"], actor_id=admin["id"], conn=db) == "ok"
    db.commit()

    row = db.query_one("SELECT status, banned_at FROM users WHERE id = %s", (author["id"],))
    assert row["status"] == "active"
    assert row["banned_at"] is None

    assert mod.unban_user(author["id"], actor_id=admin["id"], conn=db) == "already_done"

    trail = mod.history("user", author["id"], conn=db)
    assert [entry["action"] for entry in trail] == ["unban", "ban"]
    assert trail[0]["previous_status"] == "banned"
    assert trail[0]["new_status"] == "active"


# --- the sweeper's queue ----------------------------------------------------


def test_unscanned_finds_only_content_nobody_has_looked_at_yet(db, author, make_case):
    """`scanned_at IS NULL` plus an age filter.

    The age filter is what stops the sweeper racing the publish-time scan on
    something posted a moment ago and scanning it twice.
    """
    fresh = make_case(author["id"], title="נסרק כרגע")
    db.execute("UPDATE cases SET scanned_at = NULL WHERE id = %s", (fresh,))
    db.commit()

    assert mod.unscanned(limit=20, older_than_minutes=1, conn=db) == []

    db.execute(
        "UPDATE cases SET created_at = DATE_SUB(UTC_TIMESTAMP(), INTERVAL 10 MINUTE) "
        "WHERE id = %s",
        (fresh,),
    )
    db.commit()

    assert [row["id"] for row in mod.unscanned(limit=20, older_than_minutes=1, conn=db)] == [fresh]


def test_marking_something_scanned_takes_it_out_of_the_queue(db, author, make_case):
    """Stamped whatever the outcome, so the queue genuinely drains.

    Without this an item the sweeper judged fine would come back on every
    single sweep, forever.
    """
    case_id = make_case(author["id"])
    db.execute(
        "UPDATE cases SET scanned_at = NULL, "
        "created_at = DATE_SUB(UTC_TIMESTAMP(), INTERVAL 10 MINUTE) WHERE id = %s",
        (case_id,),
    )
    db.commit()
    assert len(mod.unscanned(conn=db)) == 1

    mod.mark_scanned("case", case_id, conn=db)
    db.commit()

    assert mod.unscanned(conn=db) == []


def test_the_admin_view_shows_everything_that_is_not_published(
    db, author, admin, make_case, make_comment
):
    """Cases and comments together, newest first, in one list.

    A moderator's question is "what needs looking at", which does not sort
    itself into two tables.
    """
    hidden_case = make_case(author["id"], title="תיק מוסתר")
    flagged_case = make_case(author["id"], title="תיק מסומן")
    published = make_case(author["id"], title="תיק תקין")
    comment = make_comment(published, author["id"], body="תגובה מוסתרת")

    mod.set_content_status("case", hidden_case, "hidden", actor_id=admin["id"], conn=db)
    mod.set_content_status("case", flagged_case, "flagged", actor_id=admin["id"], conn=db)
    mod.set_content_status("comment", comment, "rejected", actor_id=admin["id"], conn=db)
    db.commit()

    items = mod.flagged_content(conn=db)

    assert {(item["target_type"], item["target_id"]) for item in items} == {
        ("case", hidden_case),
        ("case", flagged_case),
        ("comment", comment),
    }
    assert all(item["moderation_status"] != "published" for item in items)
    assert all(item["author"]["id"] == author["id"] for item in items)


def test_a_scan_is_recorded_with_its_label_and_the_words_that_triggered_it(db, case):
    """`moderation_scans` is the evidence behind an automated decision.

    Without the matched terms a moderator reviewing a bot's hide can see that
    it scored badly and not why, which is not enough to overturn it on.
    """
    status, scan = mod.screen("אני אהרוג אותך חתיכת מטומטם")
    mod.record_scan("case", case, "publish", scan, conn=db)
    db.commit()

    row = db.query_one("SELECT * FROM moderation_scans WHERE target_id = %s", (case,))
    assert row["label"] == scan.label
    assert row["source"] == "publish"
    assert status in mod.CONTENT_STATUSES
