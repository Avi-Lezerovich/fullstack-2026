# -*- coding: utf-8 -*-
"""What a hidden case leaks, and to whom.

This is one file rather than four because it is one property. "Hidden" is only
worth anything if it holds on every surface at once - the body, the thread, the
likers and the followers - and a leak in any one of them is the whole leak. The
three list endpoints all guard themselves by asking `get_case` first, which
means they share a single point of failure, and sharing one is exactly why they
deserve one test file that walks all of them for every kind of viewer.

Everything is driven through HTTP rather than through the services. That is
deliberate: the services return rows, and a leak would be in the *shaping* -
`shape_comment` deciding whether to include a body, `get_case` deciding whether
to return at all. Calling the service and inspecting a dict would test the
layer underneath the one that can be wrong.

Four viewers appear throughout, and they are the four that matter:

    anonymous   sees nothing hidden
    a stranger  sees nothing hidden, even signed in
    the author  sees their own hidden content in full
    an admin    sees everything, which is what makes a reversal possible
"""

from __future__ import annotations

import pytest

from app.services import moderation_service

pytestmark = pytest.mark.integration

HIDDEN_STATUSES = ["hidden", "rejected"]


@pytest.fixture
def author(make_user):
    return make_user("התובעת", "author@lolsuit.test")


@pytest.fixture
def stranger(make_user):
    return make_user("זר", "stranger@lolsuit.test")


@pytest.fixture
def viewers(app, author, stranger, admin):
    """One client per kind of viewer, each already signed in where it should be."""

    def _client(user=None):
        browser = app.test_client()
        if user is not None:
            browser.post(
                "/api/auth/login",
                json={"email": user["email"], "password": user["password"]},
            )
        return browser

    return {
        "anonymous": _client(),
        "stranger": _client(stranger),
        "author": _client(author),
        "admin": _client(admin),
    }


@pytest.fixture
def hidden_case(db, admin, author, stranger, make_case, make_comment):
    """A case with an audience, then hidden.

    The audience is the point: a like and a follow from a third party are what
    the likers and followers endpoints would leak, and they have to exist
    before the case is hidden or there would be nothing to leak.
    """
    from app.services import follows_service, likes_service

    case_id = make_case(author["id"], title="תיק שהוסתר", body="גוף התביעה הסודי")
    make_comment(case_id, stranger["id"], body="תגובה על תיק מוסתר")
    likes_service.toggle_like(case_id, stranger["id"], conn=db)
    follows_service.follow(case_id, stranger["id"], source="manual", conn=db)
    db.commit()

    moderation_service.set_content_status(
        "case", case_id, "hidden", actor_id=admin["id"], conn=db
    )
    db.commit()
    return case_id


# --- the case itself --------------------------------------------------------


@pytest.mark.parametrize("who", ["anonymous", "stranger"])
def test_a_hidden_case_is_a_404_to_everybody_else(viewers, hidden_case, who):
    """404 rather than 403, so its existence is not confirmed either.

    A 403 would say "there is something here you may not see", which for a
    filing naming somebody is itself the sensitive fact.
    """
    response = viewers[who].get(f"/api/cases/{hidden_case}")

    assert response.status_code == 404
    assert response.get_json()["code"] == "not_found"


@pytest.mark.parametrize("who", ["author", "admin"])
def test_the_author_and_an_admin_still_see_it_in_full(viewers, hidden_case, who):
    """Hidden is not deleted, and both of them need to know what was hidden.

    The author to appeal it, the admin to reverse it - a reversal decided from
    a redacted copy would not be a review.
    """
    response = viewers[who].get(f"/api/cases/{hidden_case}")

    assert response.status_code == 200
    case = response.get_json()["case"]
    assert case["body"] == "גוף התביעה הסודי"
    assert case["moderation_status"] == "hidden"


@pytest.mark.parametrize("status", HIDDEN_STATUSES)
def test_rejected_is_as_invisible_as_hidden(db, admin, viewers, hidden_case, status):
    """Two words, one visibility rule.

    They differ in who decided (a publish-time scan versus a later action), not
    in what the public can see - so a check written against the string "hidden"
    alone would leave rejected content public.
    """
    moderation_service.set_content_status(
        "case", hidden_case, status, actor_id=admin["id"], conn=db
    )
    db.commit()

    assert viewers["anonymous"].get(f"/api/cases/{hidden_case}").status_code == 404
    assert viewers["author"].get(f"/api/cases/{hidden_case}").status_code == 200


def test_a_flagged_case_stays_completely_public(db, admin, viewers, author, make_case):
    """The status that is marked and not removed.

    If flagged behaved like hidden, one borderline word would silence a filing
    and the four-status scheme would collapse into two.
    """
    case_id = make_case(author["id"], title="תיק מסומן")
    moderation_service.set_content_status(
        "case", case_id, "flagged", actor_id=admin["id"], conn=db
    )
    db.commit()

    response = viewers["anonymous"].get(f"/api/cases/{case_id}")

    assert response.status_code == 200
    assert response.get_json()["case"]["moderation_status"] == "flagged"


def test_a_hidden_case_is_absent_from_every_listing(viewers, hidden_case, author, make_case):
    """The feed filters on the same rule the single-case endpoint applies.

    Two queries, one rule - and the listing is the easier of the two to get
    wrong, because it is a WHERE clause rather than an explicit check.
    """
    visible = make_case(author["id"], title="תיק גלוי")

    for who in ("anonymous", "stranger"):
        listed = viewers[who].get("/api/cases").get_json()["cases"]
        ids = {case["id"] for case in listed}
        assert hidden_case not in ids
        assert visible in ids


def test_the_author_finds_their_hidden_filing_on_their_own_feed_and_not_the_public_one(
    viewers, hidden_case
):
    """The `OR c.author_id = %s` arm is on the personal feed only, deliberately.

    `_FOLLOWED_VISIBILITY` adds it; `PUBLIC_VISIBILITY` does not. The comment
    above it in cases_service says why: the personal feed is a private list, so
    an author keeps sight of their own hidden filing there, while the public
    feed stays public - a hidden case must not reappear in the courtroom
    listing merely because its author happens to be reading.
    """
    public = viewers["author"].get("/api/cases").get_json()["cases"]
    personal = viewers["author"].get("/api/cases/feed").get_json()["cases"]

    assert hidden_case not in {case["id"] for case in public}
    assert hidden_case in {case["id"] for case in personal}


def test_a_hidden_filing_does_not_appear_on_anyone_elses_personal_feed(
    db, viewers, hidden_case, stranger
):
    """The author arm is scoped to the reader, not to authorship in general.

    The stranger follows this case, so it would be on their personal feed if it
    were visible at all - which makes them exactly the reader who would notice
    a mistake here.
    """
    personal = viewers["stranger"].get("/api/cases/feed").get_json()["cases"]

    assert hidden_case not in {case["id"] for case in personal}


# --- the thread -------------------------------------------------------------


@pytest.mark.parametrize("who", ["anonymous", "stranger"])
def test_a_hidden_case_does_not_leak_its_comments(viewers, hidden_case, who):
    """Regression: this endpoint had no visibility guard at all.

    `list_likers` and `list_followers` both fetched the case first and answered
    404; `list_comments` went straight to `list_for_case`. And redaction alone
    does not cover it, because hiding a case does not cascade to its comments -
    the case row becomes 'hidden' and every comment on it stays 'published', so
    `shape_comment`, which reads the comment's own status, had every reason to
    hand back the bodies in full.

    The result was that a filing hidden for harassment kept the entire argument
    on it readable to anybody holding the case id, anonymously, while `/likes`
    and `/followers` - which leak far less - were both closed.
    """
    response = viewers[who].get(f"/api/cases/{hidden_case}/comments")

    assert response.status_code == 404
    assert response.get_json()["code"] == "not_found"


def test_a_case_that_is_visible_still_serves_its_thread(viewers, author, stranger, make_case, make_comment):
    """The other half of the guard, so it cannot be satisfied by refusing always.

    A `list_comments` that returned 404 unconditionally would pass the leak
    test above and silently empty every case page in the application.
    """
    case_id = make_case(author["id"])
    make_comment(case_id, stranger["id"], body="תגובה גלויה")

    response = viewers["anonymous"].get(f"/api/cases/{case_id}/comments")

    assert response.status_code == 200
    assert [comment["body"] for comment in response.get_json()["comments"]] == ["תגובה גלויה"]


def test_a_hidden_comment_keeps_its_place_in_the_thread_as_a_placeholder(
    db, admin, viewers, hidden_case, author, make_case, make_comment
):
    """Removed content leaves a hole rather than being spliced out.

    Omitting it would renumber the conversation: replies would appear to answer
    whatever came before the gap, which changes what the remaining words mean.
    """
    case_id = make_case(author["id"])
    first = make_comment(case_id, author["id"], body="ראשונה")
    offending = make_comment(case_id, author["id"], body="שנייה, פוגענית")
    make_comment(case_id, author["id"], body="שלישית")

    moderation_service.set_content_status(
        "comment", offending, "hidden", actor_id=admin["id"], conn=db
    )
    db.commit()

    comments = viewers["stranger"].get(f"/api/cases/{case_id}/comments").get_json()["comments"]

    assert [comment["id"] for comment in comments] == [first, offending, comments[2]["id"]]
    assert comments[1]["body"] is None
    assert comments[1]["is_hidden"] is True
    assert comments[0]["body"] == "ראשונה"


def test_the_author_of_a_hidden_comment_can_still_read_it_back(
    db, admin, viewers, author, stranger, make_case, make_comment
):
    """Per-comment, not per-thread: `can_see_hidden` is decided row by row.

    On a busy case that means an author sees their own removed reply and still
    sees somebody else's as a placeholder, which is the correct answer to both
    questions at once.
    """
    case_id = make_case(author["id"])
    mine = make_comment(case_id, author["id"], body="שלי, הוסתרה")
    theirs = make_comment(case_id, stranger["id"], body="שלהם, הוסתרה")

    for comment_id in (mine, theirs):
        moderation_service.set_content_status(
            "comment", comment_id, "hidden", actor_id=admin["id"], conn=db
        )
    db.commit()

    comments = viewers["author"].get(f"/api/cases/{case_id}/comments").get_json()["comments"]
    bodies = {comment["id"]: comment["body"] for comment in comments}

    assert bodies[mine] == "שלי, הוסתרה"
    assert bodies[theirs] is None


def test_an_admin_reads_every_body_in_the_thread(
    db, admin, viewers, author, stranger, make_case, make_comment
):
    """Which is the only way a removal can be reviewed."""
    case_id = make_case(author["id"])
    comment_id = make_comment(case_id, stranger["id"], body="תגובה שהוסתרה")
    moderation_service.set_content_status(
        "comment", comment_id, "hidden", actor_id=admin["id"], conn=db
    )
    db.commit()

    comments = viewers["admin"].get(f"/api/cases/{case_id}/comments").get_json()["comments"]

    assert comments[0]["body"] == "תגובה שהוסתרה"


# --- the audience -----------------------------------------------------------


@pytest.mark.parametrize("surface", ["likes", "followers"])
@pytest.mark.parametrize("who", ["anonymous", "stranger"])
def test_a_hidden_case_does_not_leak_who_was_watching_it(viewers, hidden_case, surface, who):
    """The subtlest of the four leaks, and the easiest to forget.

    Who liked a filing is a list of people who agreed with an accusation. On a
    case hidden for harassment that list is the thing most worth protecting,
    and it lives behind an endpoint that has no content of its own to redact -
    so it has to borrow the case's rule explicitly.
    """
    response = viewers[who].get(f"/api/cases/{hidden_case}/{surface}")

    assert response.status_code == 404


@pytest.mark.parametrize("surface", ["likes", "followers"])
@pytest.mark.parametrize("who", ["author", "admin"])
def test_the_author_and_an_admin_can_still_see_the_audience(viewers, hidden_case, surface, who):
    response = viewers[who].get(f"/api/cases/{hidden_case}/{surface}")

    assert response.status_code == 200
    assert len(response.get_json()["users"]) >= 1


def test_the_audience_lists_are_public_on_a_case_that_is(viewers, author, stranger, db, make_case):
    """The other half of the rule, so it cannot be satisfied by refusing always.

    A guard that returned 404 unconditionally would pass every leak test above
    and break the feature.
    """
    from app.services import likes_service

    case_id = make_case(author["id"])
    likes_service.toggle_like(case_id, stranger["id"], conn=db)
    db.commit()

    response = viewers["anonymous"].get(f"/api/cases/{case_id}/likes")

    assert response.status_code == 200
    assert [user["id"] for user in response.get_json()["users"]] == [stranger["id"]]


# --- acting on hidden content -----------------------------------------------


def test_a_hidden_case_cannot_be_liked_or_followed(db, admin, viewers, hidden_case):
    """Interaction is refused, not merely hidden.

    Allowing a like on a filing the liker cannot read would let the counter be
    driven by people acting on something they never saw - and would make the
    like notification tell its author that hidden content is still circulating.
    """
    for surface in ("like", "follow"):
        response = viewers["stranger"].post(f"/api/cases/{hidden_case}/{surface}")
        assert response.status_code == 404, surface

    assert db.query_value("SELECT COUNT(*) FROM likes WHERE case_id = %s", (hidden_case,)) == 1


def test_the_admin_dashboard_is_closed_to_everyone_but_an_admin(viewers):
    """Anonymous gets 401 and a signed-in stranger gets 403.

    Two different answers on purpose: the first means "sign in", the second
    means "signing in will not help", and collapsing them would send an
    ordinary user round a login loop that could never succeed.
    """
    assert viewers["anonymous"].get("/api/admin/queue").status_code == 401
    assert viewers["stranger"].get("/api/admin/queue").status_code == 403
    assert viewers["author"].get("/api/admin/queue").status_code == 403
    assert viewers["admin"].get("/api/admin/queue").status_code == 200
