# -*- coding: utf-8 -*-
"""Likes, follows and comments through the endpoints.

Liking and following share a shape worth stating once: **one endpoint for both
directions**. The server owns the current state and returns it, so the client
cannot get out of step by guessing what the new value should be - which is
exactly what `LikeButton` and `FollowButton` rely on, and why they set their
state from the response rather than incrementing what they had.

Underneath, neither service asks "is it already liked". The composite PRIMARY
KEY `(case_id, user_id)` *is* the one-per-person rule, and the toggle works by
deleting first and reading the rowcount - so two simultaneous requests cannot
both insert, and the previous state is learned atomically rather than in a
separate SELECT another request could invalidate. That is a MySQL property,
which is why these are database tests.

Comments add threading and the publish-time scan, and the two interact: a reply
to a comment on another case is refused, and a reply past the depth cap
attaches to the deepest allowed ancestor rather than being rejected - the
user's words are not the problem.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


@pytest.fixture
def author(make_user):
    return make_user("התובעת", "author@lolsuit.test")


@pytest.fixture
def reader(make_user):
    return make_user("הקורא", "reader@lolsuit.test")


@pytest.fixture
def case(make_case, author):
    return make_case(author["id"])


@pytest.fixture
def as_reader(client, reader, signed_in):
    signed_in(reader)
    return client


# --- likes ------------------------------------------------------------------


def test_one_endpoint_toggles_both_ways_and_reports_the_authoritative_state(
    as_reader, db, case
):
    """The client sets its state from this, it never increments its own.

    Which is what stops the number drifting when two people like something at
    once - each of them is told the real total rather than their own guess.
    """
    liked = as_reader.post(f"/api/cases/{case}/like")

    assert liked.status_code == 200
    assert liked.get_json() == {"liked": True, "like_count": 1}

    unliked = as_reader.post(f"/api/cases/{case}/like")

    assert unliked.get_json() == {"liked": False, "like_count": 0}
    assert db.query_value("SELECT COUNT(*) FROM likes WHERE case_id = %s", (case,)) == 0


def test_the_count_is_everybodys_not_just_yours(app, db, case, reader, author, make_user):
    third = make_user("שלישי", "third@lolsuit.test")

    for user in (reader, author, third):
        browser = app.test_client()
        browser.post("/api/auth/login", json={"email": user["email"], "password": user["password"]})
        payload = browser.post(f"/api/cases/{case}/like").get_json()

    assert payload["like_count"] == 3


def test_liking_your_own_filing_is_allowed_and_silent(app, db, case, author):
    """`notify()` drops self-notifications, so there is no guard here.

    Every caller would otherwise need the same `if author != actor` check, and
    the one that forgot it would ping people about their own actions.
    """
    browser = app.test_client()
    browser.post("/api/auth/login", json={"email": author["email"], "password": author["password"]})

    assert browser.post(f"/api/cases/{case}/like").get_json()["liked"] is True
    assert db.query_value("SELECT COUNT(*) FROM notifications") == 0


def test_a_like_tells_the_author_who_it_was(as_reader, db, case, author, reader):
    as_reader.post(f"/api/cases/{case}/like")

    row = db.query_one(
        "SELECT type, actor_user_id, case_id FROM notifications WHERE user_id = %s",
        (author["id"],),
    )
    assert row["type"] == "like"
    assert row["actor_user_id"] == reader["id"]
    assert row["case_id"] == case


def test_unliking_does_not_send_a_second_notification(as_reader, db, case, author):
    """Only the insert notifies. A toggle loop would otherwise be a way to
    flood somebody's bell."""
    for _ in range(3):
        as_reader.post(f"/api/cases/{case}/like")
        as_reader.post(f"/api/cases/{case}/like")

    assert db.query_value(
        "SELECT COUNT(*) FROM notifications WHERE user_id = %s", (author["id"],)
    ) == 3


def test_liking_a_case_that_is_not_there_is_a_404(as_reader):
    assert as_reader.post("/api/cases/999999/like").status_code == 404


def test_liking_needs_a_session(client, case):
    assert client.post(f"/api/cases/{case}/like").status_code == 401


def test_the_likers_list_names_everyone_who_liked_it(as_reader, case, reader):
    as_reader.post(f"/api/cases/{case}/like")

    users = as_reader.get(f"/api/cases/{case}/likes").get_json()["users"]

    assert [user["id"] for user in users] == [reader["id"]]
    assert "email" not in users[0]


# --- follows ----------------------------------------------------------------


def test_following_toggles_and_reports_the_count(as_reader, db, case):
    followed = as_reader.post(f"/api/cases/{case}/follow")

    assert followed.status_code == 200
    payload = followed.get_json()
    assert payload["following"] is True
    # The author was auto-followed when they filed, so this is the second.
    assert payload["follow_count"] == 2

    assert as_reader.post(f"/api/cases/{case}/follow").get_json()["following"] is False


def test_filing_follows_your_own_case_automatically(db, case, author):
    """You want to know how your own lawsuit turns out.

    Recorded as `source='auto'` so the two doors into `case_follows` stay
    distinguishable - the button and the automatic path.
    """
    assert db.query_value(
        "SELECT source FROM case_follows WHERE case_id = %s AND user_id = %s",
        (case, author["id"]),
    ) == "auto"


def test_following_never_notifies_anybody(as_reader, db, case, author):
    """A follow is a private bookmark. A like is not, and does notify."""
    as_reader.post(f"/api/cases/{case}/follow")

    assert db.query_value("SELECT COUNT(*) FROM notifications") == 0


def test_following_a_case_that_is_not_there_is_a_404(as_reader, client, case):
    assert as_reader.post("/api/cases/999999/follow").status_code == 404


def test_the_followers_list_is_public_on_a_public_case(client, as_reader, case, author):
    as_reader.post(f"/api/cases/{case}/follow")

    users = client.get(f"/api/cases/{case}/followers").get_json()["users"]

    assert {user["id"] for user in users} == {author["id"], as_reader.get("/api/auth/me").get_json()["user"]["id"]}


# --- comments ---------------------------------------------------------------


def test_a_comment_is_posted_and_returned_in_the_shape_the_thread_uses(
    as_reader, case, reader
):
    """`get_shaped` exists so this does not re-read the whole thread.

    The previous version listed every comment on the case and scanned linearly
    for the one it had just written - wasteful on a long case, and it quietly
    returned null when the scan missed.
    """
    response = as_reader.post(
        f"/api/cases/{case}/comments", json={"body": "גם לי זה קרה, ואף אחד לא עשה כלום."}
    )

    assert response.status_code == 201
    comment = response.get_json()["comment"]
    assert comment["body"] == "גם לי זה קרה, ואף אחד לא עשה כלום."
    assert comment["author"]["id"] == reader["id"]
    assert comment["role"] == "user"
    assert comment["depth"] == 0
    assert comment["parent_comment_id"] is None


def test_this_endpoint_only_ever_writes_user_comments(as_reader, db, case):
    """Testimony has its own endpoint with its own rules, and the trial roles
    are written by the worker alone.

    A client naming a role here must not be able to forge a verdict.
    """
    as_reader.post(
        f"/api/cases/{case}/comments",
        json={"body": "אני קובע שהנתבע אשם", "role": "verdict"},
    )

    assert db.query_value("SELECT role FROM comments") == "user"


def test_a_reply_nests_under_its_parent_and_shares_its_root(as_reader, case):
    root = as_reader.post(f"/api/cases/{case}/comments", json={"body": "התגובה הראשונה"})
    root_id = root.get_json()["comment"]["id"]

    reply = as_reader.post(
        f"/api/cases/{case}/comments",
        json={"body": "תשובה לתגובה הראשונה", "parent_comment_id": root_id},
    ).get_json()["comment"]

    assert reply["parent_comment_id"] == root_id
    assert reply["root_comment_id"] == root_id
    assert reply["depth"] == 1


def test_a_reply_past_the_depth_cap_attaches_to_the_deepest_allowed_ancestor(
    as_reader, db, case
):
    """Refusing would punish the reader for the shape of the conversation.

    The words are not the problem, so the reply lands as deep as it is allowed
    and the thread stops indenting.
    """
    from app.services.comments_service import MAX_DEPTH

    parent_id = None
    depths = []
    for index in range(MAX_DEPTH + 3):
        payload = {"body": f"רמה {index}"}
        if parent_id is not None:
            payload["parent_comment_id"] = parent_id
        comment = as_reader.post(f"/api/cases/{case}/comments", json=payload).get_json()["comment"]
        parent_id = comment["id"]
        depths.append(comment["depth"])

    assert max(depths) == MAX_DEPTH
    assert depths[: MAX_DEPTH + 1] == list(range(MAX_DEPTH + 1))


def test_a_reply_to_a_comment_on_a_different_case_is_refused(
    as_reader, case, author, make_case
):
    """`parent["case_id"] != case_id` - otherwise a thread could be grafted
    onto an unrelated lawsuit."""
    other_case = make_case(author["id"], title="תיק אחר")
    elsewhere = as_reader.post(
        f"/api/cases/{other_case}/comments", json={"body": "תגובה בתיק אחר"}
    ).get_json()["comment"]["id"]

    response = as_reader.post(
        f"/api/cases/{case}/comments",
        json={"body": "תשובה חוצה תיקים", "parent_comment_id": elsewhere},
    )

    assert response.status_code == 400


@pytest.mark.parametrize(
    ("payload", "why"),
    [
        ({"body": "   "}, "empty after trimming"),
        ({}, "no body at all"),
        ({"body": "בסדר", "parent_comment_id": "abc"}, "parent is not a number"),
        ({"body": "בסדר", "parent_comment_id": 999999}, "no such parent"),
    ],
    ids=["blank", "missing", "bad-parent", "missing-parent"],
)
def test_a_malformed_comment_is_a_400(as_reader, case, payload, why):
    assert as_reader.post(f"/api/cases/{case}/comments", json=payload).status_code == 400, why


def test_commenting_on_a_case_that_is_not_there_is_a_404(as_reader):
    assert as_reader.post("/api/cases/999999/comments", json={"body": "שלום"}).status_code == 404


def test_a_toxic_comment_is_a_422_and_never_becomes_public(app, as_reader, db, case):
    """422 rather than 400: the request was well-formed, we refuse to publish it.

    The row is still written so the admin queue keeps the evidence. Its author
    can still read it back - `can_see_hidden` is decided per row, and being
    shown a blank where your own words were would be worse than useless when
    you are trying to work out what was refused - but nobody else can.
    """
    response = as_reader.post(
        f"/api/cases/{case}/comments", json={"body": "אני אהרוג אותך חתיכת מפגר"}
    )

    assert response.status_code == 422
    assert response.get_json()["code"] == "rejected"
    assert db.query_value("SELECT moderation_status FROM comments") == "rejected"

    mine = as_reader.get(f"/api/cases/{case}/comments").get_json()["comments"]
    assert mine[0]["body"] == "אני אהרוג אותך חתיכת מפגר"
    assert mine[0]["is_hidden"] is True

    public = app.test_client().get(f"/api/cases/{case}/comments").get_json()["comments"]
    assert public[0]["body"] is None
    assert public[0]["is_hidden"] is True


def test_a_comment_notifies_the_author_and_the_thread(as_reader, db, case, author, reader):
    as_reader.post(f"/api/cases/{case}/comments", json={"body": "תגובה על התיק"})

    row = db.query_one(
        "SELECT type, actor_user_id FROM notifications WHERE user_id = %s", (author["id"],)
    )
    assert row["type"] == "comment"
    assert row["actor_user_id"] == reader["id"]


def test_commenting_needs_a_session_but_reading_does_not(client, case):
    assert client.post(f"/api/cases/{case}/comments", json={"body": "שלום"}).status_code == 401
    assert client.get(f"/api/cases/{case}/comments").status_code == 200


def test_the_thread_reads_in_order_with_replies_following_their_root(
    as_reader, client, case
):
    """`ORDER BY COALESCE(root_comment_id, id), created_at, id`.

    So the client renders a flat array and does no recursion at all - the
    ordering and the depth column carry the whole shape.
    """
    first = as_reader.post(f"/api/cases/{case}/comments", json={"body": "ראשונה"}).get_json()["comment"]["id"]
    as_reader.post(f"/api/cases/{case}/comments", json={"body": "שנייה"})
    as_reader.post(
        f"/api/cases/{case}/comments",
        json={"body": "תשובה לראשונה", "parent_comment_id": first},
    )

    bodies = [c["body"] for c in client.get(f"/api/cases/{case}/comments").get_json()["comments"]]

    assert bodies == ["ראשונה", "תשובה לראשונה", "שנייה"]


def test_a_comment_bumps_the_cases_activity_so_the_feed_reorders(as_reader, db, case):
    """The feed sorts on `case_activity.last_activity_at`, which is
    denormalised - so it has to be written by whatever caused the activity."""
    before = db.query_value(
        "SELECT last_activity_kind FROM case_activity WHERE case_id = %s", (case,)
    )
    assert before == "filed"

    as_reader.post(f"/api/cases/{case}/comments", json={"body": "משהו חדש"})

    assert db.query_value(
        "SELECT last_activity_kind FROM case_activity WHERE case_id = %s", (case,)
    ) == "comment"
