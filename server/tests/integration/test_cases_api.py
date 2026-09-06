# -*- coding: utf-8 -*-
"""Filing a lawsuit, and reading the courtroom feed.

Two things here are worth an HTTP test rather than a service one.

**Naming a real person as defendant.** A filing may name a registered user,
which unlocks defence witnesses and a verdict that lands on a real account - so
the endpoint validates that person before the service ever sees them. Every
refusal on that path is a 400 with its own sentence, and the reason they are
separate is that they are separate mistakes: a malformed id is a client bug, a
suspended account is a stale user list, and suing yourself is a misunderstanding.

**The status filter, which #44 taught to name several statuses at once.** The
feed's "הוכרעו" tab means `verdict_reached` AND `closed` - one thing to a
reader and two rows to the database - and `list_cases` and `count_cases` share
one clause builder so the total cannot drift from the rows. Its unit test
asserts the SQL; this asserts the answer. And an unknown status is now a **400
rather than a silently empty court**, because a mistyped filter that matches
nothing looks exactly like a court with nothing in it.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration

FILING = {
    "title": "התביעה נגד השכן מלמעלה",
    "body": "הוא מזיז רהיטים בשלוש לפנות בוקר, ואינו מכיר בכך שזה קורה.",
    "defendant_text": "השכן מלמעלה",
    "charges": ["הפרעה למנוחת הציבור"],
}


@pytest.fixture
def author(make_user):
    return make_user("התובעת", "author@lolsuit.test")


@pytest.fixture
def defendant(make_user):
    return make_user("הנתבע", "defendant@lolsuit.test")


@pytest.fixture
def as_author(client, author, signed_in):
    signed_in(author)
    return client


# --- filing -----------------------------------------------------------------


def test_a_filing_opens_into_the_witness_phase_with_a_deadline(as_author, db):
    """`filed` exists in the ENUM and is written by nothing.

    There is no moment worth modelling between "submitted" and "open for
    witnesses", so the case arrives already running.
    """
    response = as_author.post("/api/cases", json=FILING)

    assert response.status_code == 201
    case = response.get_json()["case"]
    assert case["status"] == "witness_phase"
    assert case["phase_deadline_at"] is not None
    assert case["charges"] == ["הפרעה למנוחת הציבור"]
    assert case["moderation_status"] == "published"
    # Filing auto-follows, so the author hears about their own verdict.
    assert case["viewer_is_following"] is True


@pytest.mark.parametrize(
    ("payload", "why"),
    [
        ({**FILING, "title": "אב"}, "title under three characters"),
        ({**FILING, "body": "קצר"}, "body under ten characters"),
        ({**FILING, "defendant_text": "   "}, "nobody named"),
        ({}, "nothing at all"),
    ],
    ids=["short-title", "short-body", "no-defendant", "empty"],
)
def test_an_incomplete_filing_is_refused_and_written_nowhere(as_author, db, payload, why):
    before = db.query_value("SELECT COUNT(*) FROM cases")

    assert as_author.post("/api/cases", json=payload).status_code == 400, why
    assert db.query_value("SELECT COUNT(*) FROM cases") == before


def test_naming_a_registered_user_links_the_filing_to_their_account(
    as_author, db, defendant
):
    """Which is what unlocks defence witnesses and a verdict that lands.

    The defendant is returned as an object rather than a name, so the card can
    link to the profile.
    """
    response = as_author.post(
        "/api/cases", json={**FILING, "defendant_user_id": defendant["id"]}
    )

    assert response.status_code == 201
    case = response.get_json()["case"]
    assert case["defendant"]["id"] == defendant["id"]
    assert case["defendant"]["name"] == "הנתבע"


def test_a_named_defendant_fills_in_the_free_text_when_it_was_left_empty(
    as_author, defendant
):
    """So the card reads the same whether a real account was named or not.

    Everything downstream - the feed, the verdict comment, the notification -
    reads `defendant_text`, and leaving it blank would render a filing against
    nobody.
    """
    response = as_author.post(
        "/api/cases",
        json={**FILING, "defendant_text": "", "defendant_user_id": defendant["id"]},
    )

    assert response.status_code == 201
    assert response.get_json()["case"]["defendant_text"] == "הנתבע"


def test_you_cannot_sue_yourself(as_author, db, author):
    """The CHECK constraint MySQL 8 refused, enforced at the edge as well.

    `create_case` refuses it too - this is the layer that turns the refusal
    into a sentence the composer can show.
    """
    response = as_author.post(
        "/api/cases", json={**FILING, "defendant_user_id": author["id"]}
    )

    assert response.status_code == 400
    assert "עצמך" in response.get_json()["error"]
    assert db.query_value("SELECT COUNT(*) FROM cases") == 0


@pytest.mark.parametrize("value", ["abc", "", [], {"id": 1}], ids=["text", "empty", "list", "object"])
def test_a_defendant_id_that_is_not_a_number_is_refused_on_its_own_terms(as_author, value):
    """A separate message from "that person does not exist".

    One is a client bug and the other is a stale user list, and the composer
    can only tell the user which if the server tells it.
    """
    response = as_author.post("/api/cases", json={**FILING, "defendant_user_id": value})

    assert response.status_code == 400
    assert "תקין" in response.get_json()["error"]


def test_naming_somebody_who_is_not_there_or_is_suspended_is_refused(
    as_author, db, make_user
):
    """A banned account cannot be sued.

    It has no profile, no way to answer, and no way to summon a witness - so a
    filing against it would be a trial with one side absent by construction.
    """
    banned = make_user("מושעה", "banned@lolsuit.test", status="banned")

    missing = as_author.post("/api/cases", json={**FILING, "defendant_user_id": 999_999})
    suspended = as_author.post("/api/cases", json={**FILING, "defendant_user_id": banned["id"]})

    assert missing.status_code == suspended.status_code == 400
    assert missing.get_json() == suspended.get_json()
    assert db.query_value("SELECT COUNT(*) FROM cases") == 0


def test_a_toxic_filing_is_a_422_and_never_publishes(as_author, db):
    """422, not 400: the request was well-formed, we refuse to publish it.

    The row still exists for the admin queue - the evidence survives - and it
    is invisible to everybody else.
    """
    response = as_author.post(
        "/api/cases", json={**FILING, "body": "אני אהרוג אותך חתיכת מפגר, שתמות"}
    )

    assert response.status_code == 422
    assert response.get_json()["code"] == "rejected"
    assert db.query_value("SELECT moderation_status FROM cases") == "rejected"
    assert as_author.get("/api/cases").get_json()["cases"] == []


def test_filing_needs_a_session(client):
    assert client.post("/api/cases", json=FILING).status_code == 401


# --- the feed ---------------------------------------------------------------


def _file(client, title: str) -> int:
    return client.post("/api/cases", json={**FILING, "title": title}).get_json()["case"]["id"]


def test_the_feed_is_public_and_pages_with_a_matching_total(as_author, client):
    for index in range(3):
        _file(as_author, f"תביעה מספר {index}")

    payload = client.get("/api/cases?limit=2").get_json()

    assert len(payload["cases"]) == 2
    assert payload["total"] == 3
    assert payload["limit"] == 2
    assert payload["offset"] == 0


def test_the_feed_can_be_narrowed_to_one_author(as_author, client, db, author, make_case, make_user):
    other = make_user("מישהו אחר", "other@lolsuit.test")
    mine = _file(as_author, "שלי")
    make_case(other["id"], title="שלהם")

    payload = client.get(f"/api/cases?author_id={author['id']}").get_json()

    assert [case["id"] for case in payload["cases"]] == [mine]
    assert payload["total"] == 1


def test_the_decided_tab_asks_for_both_statuses_a_verdict_leaves_behind(
    as_author, client, db
):
    """A case sits in `verdict_reached` only until the worker retires it.

    Filtering on that alone showed the last few hours of judgments and hid
    every case the court had actually finished - the opposite of what a reader
    opening "הוכרעו" wants.
    """
    from app.services import cases_service

    fresh = _file(as_author, "הוכרע זה עתה")
    retired = _file(as_author, "הוכרע ונסגר")
    running = _file(as_author, "עדיין בדיון")
    db.execute("UPDATE cases SET status = 'verdict_reached' WHERE id = %s", (fresh,))
    db.execute("UPDATE cases SET status = 'closed' WHERE id = %s", (retired,))
    db.commit()

    decided = ",".join(cases_service.DECIDED_STATUSES)
    payload = client.get(f"/api/cases?status={decided}").get_json()

    assert {case["id"] for case in payload["cases"]} == {fresh, retired}
    assert running not in {case["id"] for case in payload["cases"]}


def test_the_total_means_what_the_list_means(as_author, client, db):
    """The trap `count_cases` documents, checked against the rows.

    A total counted over a wider set leaves a "load more" button offering a
    page that does not exist.
    """
    fresh = _file(as_author, "הוכרע")
    _file(as_author, "עדיין בדיון")
    db.execute("UPDATE cases SET status = 'closed' WHERE id = %s", (fresh,))
    db.commit()

    payload = client.get("/api/cases?status=closed&limit=50").get_json()

    assert payload["total"] == len(payload["cases"]) == 1


def test_one_status_still_works_on_its_own(as_author, client, db):
    """The single-value path is an equality test rather than an IN clause, so
    it is a different branch and worth its own case."""
    case_id = _file(as_author, "בשלב העדויות")

    payload = client.get("/api/cases?status=witness_phase").get_json()

    assert [case["id"] for case in payload["cases"]] == [case_id]


@pytest.mark.parametrize(
    "status",
    ["nonsense", "verdict_reached,nonsense", "filed;DROP TABLE users"],
    ids=["unknown", "one-bad-of-two", "injection-shaped"],
)
def test_an_unknown_status_is_a_400_rather_than_a_silently_empty_court(client, status):
    """Rejected rather than ignored.

    A mistyped filter that matches nothing looks exactly like an empty court,
    and the client has no way to tell the two apart.
    """
    response = client.get(f"/api/cases?status={status}")

    assert response.status_code == 400
    assert response.get_json()["code"] == "invalid"


def test_an_empty_status_filter_is_no_filter_at_all(as_author, client):
    """Blank entries are dropped, so `?status=` is not an error.

    The tab component sends an empty string for "all", which would otherwise
    be a 400 on the default view.
    """
    _file(as_author, "תביעה")

    assert len(client.get("/api/cases?status=").get_json()["cases"]) == 1
    assert len(client.get("/api/cases?status=,,").get_json()["cases"]) == 1


def test_the_personal_feed_holds_what_the_reader_follows(as_author, app, db, author):
    """Ordered by activity rather than by phase - "something has moved" is the
    question it answers.

    A separate client for the anonymous half: `as_author` IS the shared `client`
    with a session already on it, so asking it would be asking the same browser.
    """
    mine = _file(as_author, "שלי")

    payload = as_author.get("/api/cases/feed").get_json()

    assert [case["id"] for case in payload["cases"]] == [mine]
    assert set(payload) == {"cases", "total", "limit", "offset"}

    # Unlike /cases, this one is personal and has nothing to show a stranger.
    assert app.test_client().get("/api/cases/feed").status_code == 401
