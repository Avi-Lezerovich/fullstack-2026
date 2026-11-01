# -*- coding: utf-8 -*-
"""Following people, through the endpoints, and what it does to "My Feed".

The feed used to be exactly the cases a viewer follows. Following a person
widens it: every case that person files shows up too, without the viewer
having to follow each one - and unfollowing them takes those cases back out,
unless the viewer also follows a case on its own account.
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
def as_reader(client, reader, signed_in):
    signed_in(reader)
    return client


def _feed_ids(client):
    body = client.get("/api/cases/feed").get_json()
    return [c["id"] for c in body["cases"]], body["total"]


def test_follow_toggles_both_ways_and_reports_the_count(as_reader, author, db):
    followed = as_reader.post(f"/api/users/{author['id']}/follow")
    assert followed.status_code == 200
    assert followed.get_json() == {"following": True, "follower_count": 1}

    unfollowed = as_reader.post(f"/api/users/{author['id']}/follow")
    assert unfollowed.get_json() == {"following": False, "follower_count": 0}
    assert db.query_value("SELECT COUNT(*) FROM user_follows") == 0


def test_you_cannot_follow_yourself(as_reader, reader):
    assert as_reader.post(f"/api/users/{reader['id']}/follow").status_code == 400


def test_following_someone_unknown_is_a_404(as_reader):
    assert as_reader.post("/api/users/999999/follow").status_code == 404


def test_following_needs_a_session(client, author):
    assert client.post(f"/api/users/{author['id']}/follow").status_code == 401


def test_the_profile_reports_both_directions(as_reader, reader, author):
    as_reader.post(f"/api/users/{author['id']}/follow")

    theirs = as_reader.get(f"/api/users/{author['id']}").get_json()["user"]
    assert theirs["follower_count"] == 1
    assert theirs["following_users_count"] == 0
    assert theirs["viewer_is_following"] is True

    mine = as_reader.get(f"/api/users/{reader['id']}").get_json()["user"]
    assert mine["following_users_count"] == 1
    assert mine["viewer_is_following"] is False

    followers = as_reader.get(f"/api/users/{author['id']}/followers").get_json()["users"]
    assert [u["id"] for u in followers] == [reader["id"]]
    following = as_reader.get(f"/api/users/{reader['id']}/following").get_json()["users"]
    assert [u["id"] for u in following] == [author["id"]]


def test_my_feed_shows_the_cases_of_people_i_follow(as_reader, author, make_case):
    first = make_case(author["id"])
    assert _feed_ids(as_reader) == ([], 0)

    as_reader.post(f"/api/users/{author['id']}/follow")
    # Filed after the follow, too: following a person is not a snapshot.
    second = make_case(author["id"])

    ids, total = _feed_ids(as_reader)
    assert sorted(ids) == sorted([first, second])
    assert total == 2


def test_a_case_followed_both_ways_appears_once(as_reader, author, make_case):
    case = make_case(author["id"])
    as_reader.post(f"/api/cases/{case}/follow")
    as_reader.post(f"/api/users/{author['id']}/follow")

    assert _feed_ids(as_reader) == ([case], 1)


def test_unfollowing_a_person_keeps_cases_followed_on_their_own(
    as_reader, author, make_case
):
    kept = make_case(author["id"])
    dropped = make_case(author["id"])
    as_reader.post(f"/api/cases/{kept}/follow")
    as_reader.post(f"/api/users/{author['id']}/follow")
    assert sorted(_feed_ids(as_reader)[0]) == sorted([kept, dropped])

    as_reader.post(f"/api/users/{author['id']}/follow")

    assert _feed_ids(as_reader) == ([kept], 1)


def test_a_hidden_filing_by_someone_i_follow_stays_hidden(as_reader, author, make_case):
    make_case(author["id"], moderation_status="hidden")
    as_reader.post(f"/api/users/{author['id']}/follow")

    assert _feed_ids(as_reader) == ([], 0)
