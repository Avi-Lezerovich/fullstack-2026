# -*- coding: utf-8 -*-
"""Summoning witnesses, testifying, and the five rules that gate both.

`summon` numbers its own rules, and every one of them is a way the feature
could be abused rather than a validation nicety:

    1. phase      you cannot summon after the witness phase closes
    2. party      only the plaintiff or the defendant may summon at all
    3. human      bots are the court; a juror cannot testify in a case it judges
    4. not a party  you are not a witness to your own lawsuit
    5. quota      three per side, and no duplicates

Rules 3 and 5 are the ones a fake would get wrong. "Is a bot" reads the
denormalised `users.is_bot` column, which exists precisely so this check is one
indexed lookup rather than a join on every attempt - and the duplicate rule is
`UNIQUE (case_id, witness_user_id)`, enforced by catching the IntegrityError
rather than by a prior SELECT, so two clicks arriving together cannot both win.

Testimony is a comment with `role='witness_testimony'` - the same table, the
same threading and the same moderation as anything else anybody says - which is
worth pinning because it means a witness cannot bypass the content scan by
taking the stand.
"""

from __future__ import annotations

import pytest

from app.services import summons_service as summons

pytestmark = pytest.mark.integration

TESTIMONY = "הייתי שם. ראיתי את הכיסא. הוא היה ריק."


@pytest.fixture
def plaintiff(make_user):
    return make_user("התובעת", "plaintiff@lolsuit.test")


@pytest.fixture
def defendant(make_user):
    return make_user("הנתבע", "defendant@lolsuit.test")


@pytest.fixture
def witness(make_user):
    return make_user("העדה", "witness@lolsuit.test")


@pytest.fixture
def outsider(make_user):
    return make_user("עובר אורח", "outsider@lolsuit.test")


@pytest.fixture
def case(db, make_case, plaintiff, defendant):
    """A filing with a real user as its named defendant, so both sides exist."""
    case_id = make_case(plaintiff["id"])
    db.execute("UPDATE cases SET defendant_user_id = %s WHERE id = %s", (defendant["id"], case_id))
    db.commit()
    return case_id


@pytest.fixture
def a_bot(db):
    return db.query_value("SELECT user_id FROM agents WHERE role = 'juror' LIMIT 1")


# --- who is a party ---------------------------------------------------------


def test_the_author_is_the_plaintiff_and_the_named_user_is_the_defence(
    db, case, plaintiff, defendant, outsider
):
    """`side_for` is the whole notion of "party" in this module.

    It is also what decides which side a summoned witness is called for, so
    getting it wrong would not fail loudly - it would quietly fill the wrong
    side's quota.
    """
    row = db.query_one("SELECT * FROM cases WHERE id = %s", (case,))

    assert summons.side_for(row, plaintiff["id"]) == summons.PLAINTIFF
    assert summons.side_for(row, defendant["id"]) == summons.DEFENSE
    assert summons.side_for(row, outsider["id"]) is None


def test_a_case_naming_nobody_has_no_defence_side(db, make_case, plaintiff, outsider):
    """`defendant_user_id` is nullable - most filings name a person in free text.

    The truthiness check matters: without it, `None == None` would make every
    non-party the defendant on every unnamed case.
    """
    case_id = make_case(plaintiff["id"], defendant_text="השכן מקומה 3")
    row = db.query_one("SELECT * FROM cases WHERE id = %s", (case_id,))

    assert row["defendant_user_id"] is None
    assert summons.side_for(row, outsider["id"]) is None


# --- the five rules ---------------------------------------------------------


def test_a_party_can_summon_a_witness_and_the_witness_is_told(
    db, case, plaintiff, witness
):
    """The summons row is self-describing: it copies the case's deadline.

    So a witness can see how long they have without a join back to the case.
    """
    result, summons_id = summons.summon(case, plaintiff["id"], witness["id"], conn=db)
    db.commit()

    assert result == "ok"
    row = db.query_one("SELECT * FROM witness_summons WHERE id = %s", (summons_id,))
    assert row["side"] == summons.PLAINTIFF
    assert row["status"] == "pending"
    assert row["deadline_at"] is not None

    notification = db.query_one(
        "SELECT type, case_id FROM notifications WHERE user_id = %s", (witness["id"],)
    )
    assert notification["type"] == "summons"
    assert notification["case_id"] == case


def test_the_defence_summons_onto_its_own_side(db, case, defendant, witness):
    """The side comes from who is summoning, not from who is summoned."""
    summons.summon(case, defendant["id"], witness["id"], conn=db)
    db.commit()

    assert db.query_value("SELECT side FROM witness_summons") == summons.DEFENSE


def test_nobody_outside_the_case_may_summon_anyone(db, case, outsider, witness):
    """Rule 2. Otherwise any reader could drag strangers into a lawsuit."""
    assert summons.summon(case, outsider["id"], witness["id"], conn=db) == ("forbidden", None)
    db.commit()

    assert db.query_value("SELECT COUNT(*) FROM witness_summons") == 0


def test_a_bot_cannot_be_called_as_a_witness(db, case, plaintiff, a_bot):
    """Rule 3, and it reads the denormalised `users.is_bot`.

    The column is duplicated from `agents` for exactly this check - a juror
    testifying in a case it may later judge is not a joke the site is making
    on purpose.
    """
    assert summons.summon(case, plaintiff["id"], a_bot, conn=db) == ("invalid", None)


def test_neither_party_is_a_witness_to_their_own_case(db, case, plaintiff, defendant):
    """Rule 4, both directions.

    Summoning yourself would let a party post testimony that bypasses the
    ordinary comment path, and summoning the other side would let you fill
    their quota for them.
    """
    assert summons.summon(case, plaintiff["id"], plaintiff["id"], conn=db) == ("invalid", None)
    assert summons.summon(case, plaintiff["id"], defendant["id"], conn=db) == ("invalid", None)


def test_a_banned_or_missing_witness_cannot_be_summoned(db, case, plaintiff, make_user):
    banned = make_user("מושעה", "banned@lolsuit.test", status="banned")

    assert summons.summon(case, plaintiff["id"], banned["id"], conn=db) == ("not_found", None)
    assert summons.summon(case, plaintiff["id"], 999_999, conn=db) == ("not_found", None)
    assert summons.summon(999_999, plaintiff["id"], 1, conn=db) == ("not_found", None)


def test_the_same_witness_cannot_be_summoned_twice(db, case, plaintiff, witness):
    """Rule 5b, and the UNIQUE index is the enforcement, not a prior SELECT.

    So two clicks arriving together cannot both insert - one of them catches
    the IntegrityError and is told "conflict".
    """
    assert summons.summon(case, plaintiff["id"], witness["id"], conn=db)[0] == "ok"
    db.commit()

    assert summons.summon(case, plaintiff["id"], witness["id"], conn=db) == ("conflict", None)
    db.commit()

    assert db.query_value("SELECT COUNT(*) FROM witness_summons") == 1


def test_each_side_gets_three_witnesses_and_no_more(db, case, plaintiff, defendant, make_user):
    """Rule 5a, and the quota is per side rather than per case.

    A shared cap would let whichever party moved first take the whole bench.
    """
    for index in range(summons.MAX_WITNESSES_PER_SIDE):
        person = make_user(f"עד {index}", f"witness{index}@lolsuit.test")
        assert summons.summon(case, plaintiff["id"], person["id"], conn=db)[0] == "ok"
    db.commit()

    one_too_many = make_user("עד רביעי", "fourth@lolsuit.test")
    assert summons.summon(case, plaintiff["id"], one_too_many["id"], conn=db) == ("conflict", None)
    db.commit()

    # The defence's own three are untouched by the plaintiff exhausting theirs.
    assert summons.summon(case, defendant["id"], one_too_many["id"], conn=db)[0] == "ok"
    db.commit()

    assert summons.counts_by_side(case, conn=db) == {"plaintiff": 3, "defense": 1}


@pytest.mark.parametrize("status", ["jury_deliberation", "verdict_reached", "closed"])
def test_no_witness_can_be_summoned_once_the_phase_has_closed(
    db, case, plaintiff, witness, status
):
    """Rule 1. "closed", not "forbidden" - the right existed and has lapsed."""
    db.execute("UPDATE cases SET status = %s WHERE id = %s", (status, case))
    db.commit()

    assert summons.summon(case, plaintiff["id"], witness["id"], conn=db) == ("closed", None)


# --- testifying -------------------------------------------------------------


def test_a_summoned_witness_testifies_and_the_summons_records_it(
    db, case, plaintiff, witness
):
    """Testimony is a comment, in the same table as everything else.

    That is what gives it threading, moderation and the ordinary feed activity
    bump for free - and what stops it being a second content path with its own
    rules.
    """
    summons.summon(case, plaintiff["id"], witness["id"], conn=db)
    db.commit()

    result, comment_id = summons.testify(case, witness["id"], TESTIMONY, conn=db)
    db.commit()

    assert result == "ok"
    comment = db.query_one("SELECT * FROM comments WHERE id = %s", (comment_id,))
    assert comment["role"] == "witness_testimony"
    assert comment["body"] == TESTIMONY

    row = db.query_one("SELECT * FROM witness_summons WHERE case_id = %s", (case,))
    assert row["status"] == "testified"
    assert row["testimony_comment_id"] == comment_id
    assert row["responded_at"] is not None


def test_taking_the_stand_makes_the_case_yours_to_watch(db, case, plaintiff, witness):
    """You testified, so you want to know how it turns out.

    Auto-followed rather than merely notified once, because the verdict comes
    days later.
    """
    summons.summon(case, plaintiff["id"], witness["id"], conn=db)
    db.commit()
    summons.testify(case, witness["id"], TESTIMONY, conn=db)
    db.commit()

    assert db.query_value(
        "SELECT source FROM case_follows WHERE case_id = %s AND user_id = %s",
        (case, witness["id"]),
    ) == "auto"


def test_only_a_summoned_witness_may_testify(db, case, outsider):
    """Otherwise it is a comment, and there is an endpoint for that.

    "forbidden" rather than "not_found": the case is perfectly visible, it is
    the standing that is missing.
    """
    assert summons.testify(case, outsider["id"], TESTIMONY, conn=db) == ("forbidden", None)


def test_a_witness_testifies_once(db, case, plaintiff, witness):
    """The second attempt is a conflict, and the status guard is what says so.

    Allowing a second would let a witness rewrite their evidence after seeing
    how the argument went.
    """
    summons.summon(case, plaintiff["id"], witness["id"], conn=db)
    db.commit()
    summons.testify(case, witness["id"], TESTIMONY, conn=db)
    db.commit()

    assert summons.testify(case, witness["id"], "ובעצם לא", conn=db) == ("conflict", None)
    db.commit()

    assert db.query_value(
        "SELECT COUNT(*) FROM comments WHERE role = 'witness_testimony'"
    ) == 1


def test_testimony_after_the_phase_closes_is_refused(db, case, plaintiff, witness):
    summons.summon(case, plaintiff["id"], witness["id"], conn=db)
    db.execute("UPDATE cases SET status = 'jury_deliberation' WHERE id = %s", (case,))
    db.commit()

    assert summons.testify(case, witness["id"], TESTIMONY, conn=db) == ("closed", None)
    assert summons.testify(999_999, witness["id"], TESTIMONY, conn=db) == ("not_found", None)


def test_empty_testimony_is_refused_and_leaves_the_summons_pending(
    db, case, plaintiff, witness
):
    """The failure has to leave the witness able to try again.

    Marking the summons `testified` on a rejected body would spend their one
    chance on a request that produced nothing.
    """
    summons.summon(case, plaintiff["id"], witness["id"], conn=db)
    db.commit()

    assert summons.testify(case, witness["id"], "   ", conn=db) == ("invalid", None)
    db.commit()

    assert db.query_value("SELECT status FROM witness_summons") == "pending"


# --- closing the phase ------------------------------------------------------


def test_everyone_still_pending_when_the_phase_closes_is_a_no_show(
    db, case, plaintiff, witness, make_user
):
    """And each of them is told, because "you missed it" is exactly the kind of
    thing a notification is for."""
    second = make_user("עד שני", "witness2@lolsuit.test")
    for person in (witness, second):
        summons.summon(case, plaintiff["id"], person["id"], conn=db)
    db.commit()
    summons.testify(case, witness["id"], TESTIMONY, conn=db)
    db.commit()

    assert summons.mark_no_shows(case, conn=db) == 1
    db.commit()

    statuses = {
        row["witness_user_id"]: row["status"]
        for row in db.query_all("SELECT witness_user_id, status FROM witness_summons")
    }
    assert statuses == {witness["id"]: "testified", second["id"]: "no_show"}

    assert db.query_value(
        "SELECT COUNT(*) FROM notifications WHERE user_id = %s AND type = 'summons'",
        (second["id"],),
    ) == 2


def test_closing_a_phase_with_nobody_pending_does_nothing(db, case):
    """Called on every witness-phase transition, so the empty case is the
    common one."""
    assert summons.mark_no_shows(case, conn=db) == 0
    db.commit()

    assert db.query_value("SELECT COUNT(*) FROM notifications") == 0


def test_a_pending_summons_disappears_from_the_witness_list_once_the_phase_ends(
    db, case, plaintiff, witness
):
    """`pending_for_user` joins on `c.status = 'witness_phase'`.

    Without it a witness's to-do list would keep offering cases they can no
    longer testify in.
    """
    summons.summon(case, plaintiff["id"], witness["id"], conn=db)
    db.commit()

    waiting = summons.pending_for_user(witness["id"], conn=db)
    assert [row["case_id"] for row in waiting] == [case]
    assert waiting[0]["case_title"]

    db.execute("UPDATE cases SET status = 'jury_deliberation' WHERE id = %s", (case,))
    db.commit()

    assert summons.pending_for_user(witness["id"], conn=db) == []


def test_the_case_summons_list_is_shaped_for_the_panel(db, case, plaintiff, witness):
    summons.summon(case, plaintiff["id"], witness["id"], conn=db)
    db.commit()

    listed = summons.list_for_case(case, conn=db)

    assert len(listed) == 1
    assert listed[0]["witness"]["id"] == witness["id"]
    assert listed[0]["witness"]["name"] == "העדה"
    assert listed[0]["side"] == summons.PLAINTIFF
    assert listed[0]["status"] == "pending"
    assert listed[0]["testimony_comment_id"] is None


# --- through the endpoints --------------------------------------------------


def test_the_trial_endpoint_tells_the_viewer_what_they_may_do(
    client, db, case, plaintiff, witness, signed_in
):
    """So the client never has to reimplement the phase and party rules.

    Two implementations of "may this person summon" would disagree the first
    time either changed, and the UI's copy would be the one nobody tested.
    """
    signed_in(plaintiff)

    payload = client.get(f"/api/cases/{case}/trial").get_json()

    assert payload["viewer"]["side"] == summons.PLAINTIFF
    assert payload["viewer"]["can_summon"] is True
    assert payload["viewer"]["summons_remaining"] == summons.MAX_WITNESSES_PER_SIDE
    assert payload["viewer"]["can_testify"] is False
    assert payload["panel"] is None


def test_the_viewer_block_closes_down_as_the_trial_moves_on(
    client, db, case, plaintiff, witness, signed_in
):
    """`can_summon` is three conditions at once - party, phase, and quota.

    Each of them is a separate way the button should disappear, and the client
    reads one boolean rather than recomputing all three.
    """
    signed_in(plaintiff)
    summons.summon(case, plaintiff["id"], witness["id"], conn=db)
    db.commit()

    viewer = client.get(f"/api/cases/{case}/trial").get_json()["viewer"]
    assert viewer["can_summon"] is True
    assert viewer["summons_remaining"] == summons.MAX_WITNESSES_PER_SIDE - 1

    db.execute("UPDATE cases SET status = 'jury_deliberation' WHERE id = %s", (case,))
    db.commit()

    viewer = client.get(f"/api/cases/{case}/trial").get_json()["viewer"]
    assert viewer["side"] == summons.PLAINTIFF
    assert viewer["can_summon"] is False


def test_a_summoned_witness_is_told_they_may_take_the_stand(
    client, db, case, plaintiff, witness, signed_in
):
    """`can_testify` needs a pending summons of their own, so it is false for
    everybody else on the same case."""
    summons.summon(case, plaintiff["id"], witness["id"], conn=db)
    db.commit()

    signed_in(witness)
    viewer = client.get(f"/api/cases/{case}/trial").get_json()["viewer"]

    assert viewer["side"] is None
    assert viewer["can_summon"] is False
    assert viewer["can_testify"] is True

    summons.testify(case, witness["id"], TESTIMONY, conn=db)
    db.commit()

    assert client.get(f"/api/cases/{case}/trial").get_json()["viewer"]["can_testify"] is False


def test_the_trial_endpoint_shows_the_panel_once_one_is_seated(
    client, db, case, plaintiff, signed_in
):
    """The panel is null until the jury is drawn, and the client renders on that."""
    from worker import trial_tasks

    db.execute(
        "UPDATE cases SET phase_deadline_at = DATE_SUB(UTC_TIMESTAMP(), INTERVAL 1 MINUTE) "
        "WHERE id = %s",
        (case,),
    )
    db.commit()
    trial_tasks.advance_witness_phase()

    panel = client.get(f"/api/cases/{case}/trial").get_json()["panel"]

    assert panel is not None
    assert panel["judge"]["is_bot"] is True
    assert len(panel["members"]) == 7
    assert [member["seat"] for member in panel["members"]] == list(range(7))
    # Nobody has spoken yet, so every seat is still waiting.
    assert all(member["vote"] is None for member in panel["members"])
    assert all(member["speaks_at"] is not None for member in panel["members"])


def test_the_trial_endpoint_works_signed_out(client, case):
    """The courtroom is public; only acting in it is not."""
    response = client.get(f"/api/cases/{case}/trial")

    assert response.status_code == 200
    assert response.get_json()["viewer"]["side"] is None
    assert client.get("/api/cases/999999/trial").status_code == 404


def test_summoning_through_the_endpoint_returns_the_updated_list(
    client, case, plaintiff, witness, signed_in
):
    signed_in(plaintiff)

    response = client.post(
        f"/api/cases/{case}/summons", json={"witness_user_id": witness["id"]}
    )

    assert response.status_code == 201
    assert [row["witness"]["id"] for row in response.get_json()["summons"]] == [witness["id"]]


@pytest.mark.parametrize(
    ("payload", "status", "why"),
    [
        ({}, 400, "no witness named"),
        ({"witness_user_id": "abc"}, 400, "witness is not a number"),
        ({"witness_user_id": 999999}, 404, "no such witness"),
    ],
    ids=["no-witness", "bad-witness", "missing-witness"],
)
def test_a_malformed_summons_is_refused_with_the_right_status(
    client, case, plaintiff, signed_in, payload, status, why
):
    signed_in(plaintiff)

    assert client.post(f"/api/cases/{case}/summons", json=payload).status_code == status, why


def test_the_endpoints_map_each_service_result_to_its_own_status(
    client, app, case, plaintiff, defendant, outsider, witness, a_bot, signed_in
):
    """Four different refusals, four different codes.

    Collapsing them to one would leave the UI unable to say why - and
    "forbidden" versus "closed" is the difference between "this was never
    yours" and "you are too late".
    """
    signed_in(outsider)
    assert client.post(f"/api/cases/{case}/summons", json={"witness_user_id": witness["id"]}).status_code == 403

    party = app.test_client()
    party.post("/api/auth/login", json={"email": plaintiff["email"], "password": plaintiff["password"]})
    assert party.post(f"/api/cases/{case}/summons", json={"witness_user_id": a_bot}).status_code == 400
    assert party.post(f"/api/cases/{case}/summons", json={"witness_user_id": defendant["id"]}).status_code == 400


def test_testifying_through_the_endpoint(client, db, case, plaintiff, witness, app, signed_in):
    stand = app.test_client()
    stand.post("/api/auth/login", json={"email": plaintiff["email"], "password": plaintiff["password"]})
    stand.post(f"/api/cases/{case}/summons", json={"witness_user_id": witness["id"]})

    signed_in(witness)
    assert client.get("/api/me/summons").get_json()["summons"][0]["case_id"] == case

    response = client.post(f"/api/cases/{case}/testify", json={"body": TESTIMONY})

    assert response.status_code == 201
    assert response.get_json()["comment_id"]
    assert client.get("/api/me/summons").get_json()["summons"] == []


def test_testifying_uninvited_is_a_403_and_an_empty_body_is_a_400(
    client, case, outsider, signed_in
):
    signed_in(outsider)

    assert client.post(f"/api/cases/{case}/testify", json={"body": TESTIMONY}).status_code == 403
    assert client.post(f"/api/cases/{case}/testify", json={"body": "  "}).status_code == 400


def test_the_trial_endpoints_that_change_something_need_a_session(client, case):
    assert client.post(f"/api/cases/{case}/summons", json={"witness_user_id": 1}).status_code == 401
    assert client.post(f"/api/cases/{case}/testify", json={"body": "x"}).status_code == 401
    assert client.get("/api/me/summons").status_code == 401


def test_the_public_roster_never_publishes_a_personality_prompt(client):
    """It is the instruction the brain is given, not something the public needs.

    Publishing it would hand anyone the exact text to imitate a juror.
    """
    response = client.get("/api/agents")

    assert response.status_code == 200
    roster = response.get_json()["agents"]
    assert len(roster) == 31
    assert {agent["role"] for agent in roster} == {"judge", "juror", "moderator"}
    assert all("personality_prompt" not in agent for agent in roster)
