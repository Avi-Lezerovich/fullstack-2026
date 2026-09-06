# -*- coding: utf-8 -*-
"""Withdrawing a filing, through the endpoint, with a real session cookie.

This replaces `test_post_delete_flow.py`, whose four scenarios were all still
correct and whose every mechanism was not. It drove `/api/posts`, which has not
existed since the rename; it read a bare JSON array back from the list
endpoint, which now returns an envelope; and it built a *second* Flask app
inside one test and relied on both apps' `services.get_db` resolving to the
same monkeypatched SQLite file - a trick that only worked because of a
module-level seam this codebase deliberately removed.

None of that is needed here. Two clients against one MySQL database are two
clients against one database, which is what the scenario was reaching for in
the first place.

What is worth testing at this level rather than at the service level is the
mapping from result code to status: `delete_case` returns four strings, and the
route turns them into 200 / 403 / 404 / 409. `closed` becoming 409 rather than
403 is the one that carries meaning - the author had the right and lost it.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration

FILING = {
    "title": "תביעה נגד מי שלקח את הכיסא",
    "body": "ישבתי שם רגע אחד וכשחזרתי הכיסא היה תפוס. זו לא טעות, זו כוונה.",
    "defendant_text": "היושב החדש",
    "charges": ["גזל כיסא"],
}


def _file_a_case(client) -> int:
    response = client.post("/api/cases", json=FILING)
    assert response.status_code == 201, response.get_json()
    return response.get_json()["case"]["id"]


def test_the_author_withdraws_their_own_filing_and_it_leaves_the_feed(
    client, make_user, signed_in
):
    """The round trip a user actually performs, end to end.

    Asserting it is gone from `/api/cases` as well as from `/api/cases/<id>`
    is the part worth keeping: a delete that removed the row but left it in a
    cached listing would pass a narrower test.
    """
    signed_in(make_user("התובעת", "author@lolsuit.test"))
    case_id = _file_a_case(client)

    assert client.get(f"/api/cases/{case_id}").status_code == 200

    response = client.delete(f"/api/cases/{case_id}")

    assert response.status_code == 200
    assert response.get_json() == {"ok": True}
    assert client.get(f"/api/cases/{case_id}").status_code == 404

    listing = client.get("/api/cases").get_json()
    assert case_id not in {case["id"] for case in listing["cases"]}


def test_one_user_cannot_withdraw_another_users_filing(app, make_user, signed_in):
    """Two browsers, one database - which is all the old test's second Flask
    app was ever standing in for.

    The filing must still be there afterwards, not merely refused: a 403 that
    deleted anyway would pass an assertion on the status code alone.
    """
    author_client = app.test_client()
    author = make_user("התובעת", "author@lolsuit.test")
    author_client.post(
        "/api/auth/login", json={"email": author["email"], "password": author["password"]}
    )
    case_id = _file_a_case(author_client)

    signed_in(make_user("עובר אורח", "stranger@lolsuit.test"))
    intruder = app.test_client()
    stranger = make_user("סקרן", "curious@lolsuit.test")
    intruder.post(
        "/api/auth/login", json={"email": stranger["email"], "password": stranger["password"]}
    )

    response = intruder.delete(f"/api/cases/{case_id}")

    assert response.status_code == 403
    assert response.get_json()["code"] == "forbidden"
    assert author_client.get(f"/api/cases/{case_id}").status_code == 200


def test_withdrawing_a_filing_that_does_not_exist_is_a_404(client, make_user, signed_in):
    signed_in(make_user("התובעת", "author@lolsuit.test"))

    response = client.delete("/api/cases/999999")

    assert response.status_code == 404
    assert response.get_json()["code"] == "not_found"


def test_an_anonymous_request_is_rejected_before_the_case_is_even_looked_up(client, db):
    """401 for a case that exists, so the answer cannot be used as a probe.

    An anonymous DELETE that returned 404 for a missing case and 401 for a real
    one would let anybody enumerate which case ids exist without signing in.
    """
    response = client.delete("/api/cases/999999")
    assert response.status_code == 401
    assert response.get_json()["code"] == "unauthorized"


def test_a_withdrawal_after_the_jury_is_seated_is_a_conflict_not_a_refusal(
    client, db, make_user, signed_in
):
    """409, and a message about the phase rather than about permission.

    This branch did not exist when the old test was written - `delete_post` had
    no notion of a trial - so it is the one genuinely new assertion in the file.
    """
    signed_in(make_user("התובעת", "author@lolsuit.test"))
    case_id = _file_a_case(client)

    db.execute("UPDATE cases SET status = 'jury_deliberation' WHERE id = %s", (case_id,))
    db.commit()

    response = client.delete(f"/api/cases/{case_id}")

    assert response.status_code == 409
    assert response.get_json()["code"] == "closed"
    assert client.get(f"/api/cases/{case_id}").status_code == 200
