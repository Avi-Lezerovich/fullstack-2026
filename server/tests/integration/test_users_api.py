# -*- coding: utf-8 -*-
"""Profiles, the directory, and the two endpoints about what the bots remember.

Three things here are worth a test rather than a glance.

**An email address is private even from signed-in strangers.** `public_user`
and `private_user` differ by exactly one key, and the difference is the whole
privacy boundary of this application - so it is asserted on the endpoints that
serve each, not on the shaping functions where it would be tautological.

**A count and the list behind it are built from one WHERE clause.** `/users`
and `/users/<id>/follows` each return a `total` alongside their page, and
`_search_where` / `_FOLLOWED_VISIBILITY` exist so the two cannot disagree. A
page that counts more rows than it can ever show is a "load more" button that
never stops - so both are asserted against each other rather than against a
literal.

**A bot's record is public and a human's memories are not.** They come from the
same `agent_events` table, and which one you get depends on `is_bot`. A bot's
history *is* the site; a human's episode rows are what the bots remember about
them, they mention other people, and they are readable only by their subject.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


@pytest.fixture
def person(make_user):
    return make_user("דנה קוסטלו־בר", "dana@lolsuit.test")


@pytest.fixture
def other(make_user):
    return make_user("יוסי לוי", "yossi@lolsuit.test")


@pytest.fixture
def a_bot(db):
    return db.query_one(
        "SELECT u.id, u.name FROM users u JOIN agents a ON a.user_id = u.id "
        "WHERE a.role = 'judge' LIMIT 1"
    )


# --- the directory ----------------------------------------------------------


def test_the_directory_is_public_and_pages_with_a_matching_total(client, db, person):
    """`total` is what lets the page past the first fifty.

    It counts the same filters the list applies, so paging can terminate.
    """
    payload = client.get("/api/users?limit=5").get_json()

    assert len(payload["users"]) == 5
    assert payload["limit"] == 5
    assert payload["offset"] == 0
    assert payload["total"] == db.query_value(
        "SELECT COUNT(*) FROM users WHERE status = 'active'"
    )


def test_paging_the_directory_walks_the_whole_list_without_repeating(client):
    """The ORDER BY is stable (`is_bot`, then name), which is what makes
    offset paging correct rather than merely plausible."""
    first = client.get("/api/users?limit=5&offset=0").get_json()["users"]
    second = client.get("/api/users?limit=5&offset=5").get_json()["users"]

    assert len({user["id"] for user in first + second}) == 10


def test_the_directory_can_be_searched_by_name(client, person, other):
    found = client.get("/api/users?search=קוסטלו").get_json()

    assert [user["id"] for user in found["users"]] == [person["id"]]
    assert found["total"] == 1


def test_the_summons_dialog_can_ask_for_humans_only(client, db, person):
    """Bots are not eligible witnesses, so offering them is offering a dead end.

    The filter and its count move together - `include_bots=0` has to narrow
    both or the dialog pages into nothing.
    """
    everyone = client.get("/api/users").get_json()
    humans = client.get("/api/users?include_bots=0").get_json()

    assert humans["total"] < everyone["total"]
    assert all(user["is_bot"] is False for user in humans["users"])
    assert humans["total"] == db.query_value(
        "SELECT COUNT(*) FROM users WHERE status = 'active' AND is_bot = 0"
    )


def test_the_directory_never_publishes_an_email_address(client, person):
    """Private even from signed-in strangers - `public_user` omits the key
    entirely rather than blanking it."""
    users = client.get("/api/users?search=קוסטלו").get_json()["users"]

    assert "email" not in users[0]
    assert "password_hash" not in users[0]


def test_a_nonsense_page_size_falls_back_rather_than_failing(client):
    """`positive_int` clamps instead of raising.

    A client sending `limit=-1` or `limit=banana` should get the first page,
    not a 500 - and `limit=9999` should get the cap rather than the whole table.
    """
    for query in ("limit=abc", "limit=-5", "offset=-1"):
        assert client.get(f"/api/users?{query}").status_code == 200

    capped = client.get("/api/users?limit=9999").get_json()
    assert len(capped["users"]) <= 50


# --- one profile ------------------------------------------------------------


def test_a_profile_carries_the_counts_the_page_renders(client, db, person, make_case):
    make_case(person["id"])
    make_case(person["id"])

    profile = client.get(f"/api/users/{person['id']}").get_json()["user"]

    assert profile["name"] == "דנה קוסטלו־בר"
    assert profile["case_count"] == 2
    # Filing auto-follows, so they are tracking both of their own.
    assert profile["following_count"] == 2
    assert "email" not in profile


def test_a_banned_account_has_no_profile_at_all(client, db, person):
    assert client.get(f"/api/users/{person['id']}").status_code == 200

    db.execute("UPDATE users SET status = 'banned' WHERE id = %s", (person["id"],))
    db.commit()

    assert client.get(f"/api/users/{person['id']}").status_code == 404
    assert client.get("/api/users/999999").status_code == 404


def test_reading_a_stranger_profile_never_reveals_their_hidden_filings(
    client, db, person, admin, make_case
):
    """`viewer_id` is who is asking, not whose list it is.

    The count and the list behind it both use it, so a hidden filing is absent
    from both - and the number on the profile matches what the list shows.
    """
    visible = make_case(person["id"])
    hidden = make_case(person["id"])

    from app.services import moderation_service

    moderation_service.set_content_status(
        "case", hidden, "hidden", actor_id=admin["id"], conn=db
    )
    db.commit()

    profile = client.get(f"/api/users/{person['id']}").get_json()["user"]
    follows = client.get(f"/api/users/{person['id']}/follows").get_json()

    assert profile["following_count"] == 1
    assert follows["total"] == 1
    assert [case["id"] for case in follows["cases"]] == [visible]


def test_the_author_sees_their_own_hidden_filing_on_their_own_profile(
    app, db, person, admin, make_case
):
    """The other side of the same `viewer_id`.

    Which is why it is the *viewer's* id rather than the profile owner's: the
    same list renders differently depending on who is reading it.
    """
    from app.services import moderation_service

    hidden = make_case(person["id"])
    moderation_service.set_content_status(
        "case", hidden, "hidden", actor_id=admin["id"], conn=db
    )
    db.commit()

    browser = app.test_client()
    browser.post(
        "/api/auth/login", json={"email": person["email"], "password": person["password"]}
    )

    follows = browser.get(f"/api/users/{person['id']}/follows").get_json()

    assert follows["total"] == 1
    assert [case["id"] for case in follows["cases"]] == [hidden]


def test_the_follows_list_pages_with_the_same_envelope_as_the_feed(
    client, person, make_case
):
    """Same shape, so the client pages it with the same hook."""
    for _ in range(3):
        make_case(person["id"])

    payload = client.get(f"/api/users/{person['id']}/follows?limit=2").get_json()

    assert set(payload) == {"cases", "total", "limit", "offset"}
    assert len(payload["cases"]) == 2
    assert payload["total"] == 3


def test_a_banned_users_follow_list_is_a_404_too(client, db, person):
    db.execute("UPDATE users SET status = 'banned' WHERE id = %s", (person["id"],))
    db.commit()

    assert client.get(f"/api/users/{person['id']}/follows").status_code == 404
    assert client.get("/api/users/999999/follows").status_code == 404


# --- the court record -------------------------------------------------------


def test_a_bots_record_is_public(client, db, a_bot):
    """A bot's history IS the site - the cases it judged are already on the
    feed, and this is the one page that gathers them."""
    from app.services import memory_service

    memory_service.record_event(
        a_bot["id"], "verdict", "פסקתי דין בתיק הכיסא", importance=5, conn=db
    )
    db.commit()

    response = client.get(f"/api/users/{a_bot['id']}/record")

    assert response.status_code == 200
    assert [row["summary"] for row in response.get_json()["record"]] == ["פסקתי דין בתיק הכיסא"]


def test_a_humans_record_is_empty_rather_than_forbidden(client, person):
    """"This person has no court record" is both true and what the profile
    page wants to render.

    A 403 would make the profile component branch on account type to decide
    whether to call the endpoint at all.
    """
    response = client.get(f"/api/users/{person['id']}/record")

    assert response.status_code == 200
    assert response.get_json() == {"record": []}


def test_a_record_is_a_glance_rather_than_a_log(client, db, a_bot):
    """Capped, and the cap is editorial rather than a saving.

    At twelve it stopped being a glance and became a log, and a log of likes
    pushes the actual profile off the screen.
    """
    from app.api.users import RECORD_LIMIT
    from app.services import memory_service

    for index in range(RECORD_LIMIT + 4):
        memory_service.record_event(a_bot["id"], "comment", f"אירוע {index}", conn=db)
    db.commit()

    record = client.get(f"/api/users/{a_bot['id']}/record").get_json()["record"]

    assert len(record) == RECORD_LIMIT


def test_a_banned_or_missing_account_has_no_record(client, db, person):
    db.execute("UPDATE users SET status = 'banned' WHERE id = %s", (person["id"],))
    db.commit()

    assert client.get(f"/api/users/{person['id']}/record").status_code == 404
    assert client.get("/api/users/999999/record").status_code == 404


# --- editing your own profile -----------------------------------------------


def test_you_can_change_your_own_name_bio_and_avatar(client, person, signed_in):
    signed_in(person)

    response = client.patch(
        "/api/users/me",
        json={"name": "דנה קוסטלו־לוי", "bio": "תובעת סדרתית", "avatar_url": "/api/uploads/x.png"},
    )

    assert response.status_code == 200
    user = response.get_json()["user"]
    assert user["name"] == "דנה קוסטלו־לוי"
    assert user["bio"] == "תובעת סדרתית"
    # Your own record, so this one DOES carry the address.
    assert user["email"] == person["email"]


def test_a_field_left_out_is_left_alone(client, person, signed_in):
    """`"name" in data` rather than a truthiness check.

    Otherwise sending only a bio would blank the name, and sending an empty
    bio deliberately would be indistinguishable from not sending one.
    """
    signed_in(person)
    client.patch("/api/users/me", json={"bio": "ביוגרפיה"})

    user = client.patch("/api/users/me", json={"avatar_url": "/api/uploads/y.png"}).get_json()["user"]

    assert user["name"] == "דנה קוסטלו־בר"
    assert user["bio"] == "ביוגרפיה"


def test_a_name_that_is_too_short_is_refused(client, person, signed_in):
    signed_in(person)

    response = client.patch("/api/users/me", json={"name": "א"})

    assert response.status_code == 400
    assert client.get(f"/api/users/{person['id']}").get_json()["user"]["name"] == "דנה קוסטלו־בר"


def test_editing_a_profile_needs_a_session(client):
    assert client.patch("/api/users/me", json={"name": "מישהו"}).status_code == 401


# --- what the court remembers about you -------------------------------------


def test_you_can_read_and_erase_what_the_bots_remember_about_you(
    client, db, person, a_bot, signed_in
):
    """Anything a site stores about somebody, that person gets to read and
    delete.

    Erasing clears only the written summaries - the messages themselves are
    still there and both sides can still read them.
    """
    from app.services import memory_service

    memory_service.save_memory(
        a_bot["id"], person["id"], summary="אוהבת חתולים", facts=[], covered_event_id=0, conn=db
    )
    db.commit()
    signed_in(person)

    assert len(client.get("/api/users/me/memories").get_json()["memories"]) == 1

    assert client.delete("/api/users/me/memories").get_json()["forgotten"] >= 1

    assert client.get("/api/users/me/memories").get_json()["memories"] == []


def test_one_persons_memories_are_never_another_persons_business(
    client, app, db, person, other, a_bot, signed_in
):
    """Deliberately scoped to `me` - there is no endpoint that takes an id."""
    from app.services import memory_service

    memory_service.save_memory(
        a_bot["id"], person["id"], summary="סוד", facts=[], covered_event_id=0, conn=db
    )
    db.commit()

    signed_in(other)

    assert client.get("/api/users/me/memories").get_json()["memories"] == []


def test_the_memory_endpoints_need_a_session(client):
    assert client.get("/api/users/me/memories").status_code == 401
    assert client.delete("/api/users/me/memories").status_code == 401
