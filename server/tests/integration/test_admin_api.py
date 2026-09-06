# -*- coding: utf-8 -*-
"""The admin dashboard, and the reporting endpoint that feeds it.

The course requires that a human can override any bot decision. That is what
`POST /admin/content/<type>/<id>/status` is, and this file is where the
requirement is actually checked end to end rather than at the service layer:
the same endpoint shape a bot's decision produced is what a human uses to
reverse it, both write to the same trail, and the trail records the previous
status so the reversal is visible afterwards.

The other reason these are HTTP tests is the permission split. `require_admin`
answers **401 to an anonymous request and 403 to a signed-in non-admin**, and
that difference is load-bearing for the client: the first means "sign in", the
second means "signing in will not help". Collapsing them sends an ordinary user
round a login loop that can never succeed, so every endpoint here is checked
against both.
"""

from __future__ import annotations

import pytest

from app.services import moderation_service as mod

pytestmark = pytest.mark.integration

ADMIN_ENDPOINTS = [
    ("get", "/api/admin/queue", None),
    ("get", "/api/admin/flagged", None),
    ("get", "/api/admin/history/case/1", None),
    ("get", "/api/admin/users/banned", None),
    ("post", "/api/admin/content/case/1/status", {"status": "hidden"}),
    ("post", "/api/admin/reports/1/resolve", {"decision": "resolved_dismissed"}),
    ("post", "/api/admin/users/1/ban", {}),
    ("post", "/api/admin/users/1/unban", {}),
]


@pytest.fixture
def author(make_user):
    return make_user("הכותב", "author@lolsuit.test")


@pytest.fixture
def reporter(make_user):
    return make_user("המדווחת", "reporter@lolsuit.test")


@pytest.fixture
def case(make_case, author):
    return make_case(author["id"])


@pytest.fixture
def as_admin(client, admin, signed_in):
    signed_in(admin)
    return client


def _status(db, case_id: int) -> str:
    return db.query_value("SELECT moderation_status FROM cases WHERE id = %s", (case_id,))


# --- who may open the dashboard ---------------------------------------------


@pytest.mark.parametrize(("method", "path", "payload"), ADMIN_ENDPOINTS)
def test_every_admin_endpoint_refuses_an_anonymous_request_with_401(
    client, method, path, payload
):
    """Sign in - which is a different instruction from "you may not".

    Answering 403 here would tell a signed-out visitor that signing in is
    pointless, and answering 401 to a signed-in user would send them round a
    login loop.
    """
    response = getattr(client, method)(path, json=payload)

    assert response.status_code == 401
    assert response.get_json()["code"] == "unauthorized"


@pytest.mark.parametrize(("method", "path", "payload"), ADMIN_ENDPOINTS)
def test_every_admin_endpoint_refuses_an_ordinary_user_with_403(
    client, author, signed_in, method, path, payload
):
    """Signing in will not help, and the message says which kind of account
    this is for."""
    signed_in(author)

    response = getattr(client, method)(path, json=payload)

    assert response.status_code == 403
    assert response.get_json()["code"] == "forbidden"


def test_a_banned_admin_loses_the_dashboard_immediately(
    client, db, admin, signed_in, make_user
):
    """`require_admin` resolves the session first, and `resolve_session`
    refuses a banned account - so a suspended admin is anonymous again on the
    very next request, not merely un-privileged."""
    signed_in(admin)
    assert client.get("/api/admin/queue").status_code == 200

    db.execute("UPDATE users SET status = 'banned' WHERE id = %s", (admin["id"],))
    db.commit()

    assert client.get("/api/admin/queue").status_code == 401


# --- reporting --------------------------------------------------------------


def test_anybody_signed_in_can_report_something(client, case, reporter, signed_in):
    signed_in(reporter)

    response = client.post(
        "/api/reports",
        json={"target_type": "case", "target_id": case, "reason": "abuse", "details": "פוגעני"},
    )

    assert response.status_code == 201
    assert response.get_json()["report_id"]


def test_reporting_the_same_thing_twice_is_a_409(client, case, reporter, signed_in):
    """One report per person per target, so the queue cannot be flooded."""
    signed_in(reporter)
    payload = {"target_type": "case", "target_id": case, "reason": "abuse"}

    assert client.post("/api/reports", json=payload).status_code == 201
    duplicate = client.post("/api/reports", json=payload)

    assert duplicate.status_code == 409
    assert duplicate.get_json()["code"] == "conflict"


@pytest.mark.parametrize(
    ("payload", "status", "why"),
    [
        ({"target_type": "case"}, 400, "no target id"),
        ({"target_type": "case", "target_id": "abc"}, 400, "target id is not a number"),
        ({"target_type": "post", "target_id": 1}, 400, "unsupported target type"),
        ({"target_type": "case", "target_id": 999999}, 404, "no such case"),
    ],
    ids=["no-id", "bad-id", "bad-type", "missing-case"],
)
def test_a_malformed_report_is_refused(client, reporter, signed_in, payload, status, why):
    signed_in(reporter)

    assert client.post("/api/reports", json=payload).status_code == status, why


def test_an_unrecognised_reason_becomes_other_rather_than_an_error(
    as_admin, client, db, case, reporter, signed_in
):
    """The reason is a hint for a human, not a control.

    Refusing an unknown one would make the report form's dropdown a contract
    that has to be versioned alongside the server.
    """
    signed_in(reporter)

    client.post(
        "/api/reports",
        json={"target_type": "case", "target_id": case, "reason": "כי בא לי"},
    )

    assert db.query_value("SELECT reason FROM reports") == "other"


def test_reporting_needs_a_session(client, case):
    assert client.post(
        "/api/reports", json={"target_type": "case", "target_id": case}
    ).status_code == 401


# --- the queue --------------------------------------------------------------


def test_the_queue_lists_reports_with_everything_needed_to_judge_them(
    as_admin, db, case, reporter
):
    mod.report("case", case, reporter["id"], "abuse", details="לשון הרע", conn=db)
    db.commit()

    reports = as_admin.get("/api/admin/queue").get_json()["reports"]

    assert len(reports) == 1
    assert reports[0]["target_type"] == "case"
    assert reports[0]["target_id"] == case
    assert reports[0]["details"] == "לשון הרע"
    assert reports[0]["reporter"]["name"] == "המדווחת"
    assert reports[0]["excerpt"]
    assert reports[0]["case_id"] == case


def test_the_queue_can_be_narrowed_to_a_status(as_admin, db, case, reporter, admin):
    _, report_id = mod.report("case", case, reporter["id"], "abuse", conn=db)
    db.commit()

    assert len(as_admin.get("/api/admin/queue?status=open").get_json()["reports"]) == 1
    assert as_admin.get("/api/admin/queue?status=resolved").get_json()["reports"] == []

    mod.resolve_report(report_id, mod.RESOLVED_DISMISSED, resolver_id=admin["id"], conn=db)
    db.commit()

    assert as_admin.get("/api/admin/queue?status=open").get_json()["reports"] == []
    assert len(as_admin.get("/api/admin/queue?status=resolved").get_json()["reports"]) == 1


def test_the_flagged_view_gathers_everything_that_is_not_published(
    as_admin, db, case, admin, author, make_case, make_comment
):
    """Cases and comments in one list, because "what needs looking at" does not
    sort itself into two tables."""
    comment_id = make_comment(case, author["id"])
    mod.set_content_status("case", case, "flagged", actor_id=admin["id"], conn=db)
    mod.set_content_status("comment", comment_id, "hidden", actor_id=admin["id"], conn=db)
    db.commit()

    items = as_admin.get("/api/admin/flagged").get_json()["items"]

    assert {(item["target_type"], item["target_id"]) for item in items} == {
        ("case", case),
        ("comment", comment_id),
    }


# --- the override -----------------------------------------------------------


def test_an_admin_can_hide_content_and_then_put_it_back(as_admin, db, case):
    """The override the course requires, in one round trip each way."""
    hidden = as_admin.post(
        f"/api/admin/content/case/{case}/status",
        json={"status": "hidden", "reason": "לשון הרע"},
    )

    assert hidden.status_code == 200
    assert hidden.get_json() == {"ok": True, "status": "hidden", "changed": True}
    assert _status(db, case) == "hidden"

    restored = as_admin.post(
        f"/api/admin/content/case/{case}/status", json={"status": "published"}
    )

    assert restored.get_json()["changed"] is True
    assert _status(db, case) == "published"


def test_re_applying_the_status_something_already_has_reports_no_change(as_admin, db, case):
    """"changed": false, and still a 200.

    Two moderators clicking the same button is not an error; it is the normal
    outcome of a shared queue.
    """
    as_admin.post(f"/api/admin/content/case/{case}/status", json={"status": "hidden"})

    again = as_admin.post(f"/api/admin/content/case/{case}/status", json={"status": "hidden"})

    assert again.status_code == 200
    assert again.get_json()["changed"] is False


def test_the_override_is_recorded_as_an_override_with_where_it_came_from(
    as_admin, db, case, admin, make_user
):
    """Which is what makes "a human reversed a bot" a thing the record says.

    The route passes `action="override"` explicitly rather than letting the
    verb be derived, so a human decision is distinguishable in the trail from
    an identical automated one.
    """
    sweeper = make_user("סורק", "sweeper@lolsuit.test", is_bot=True)
    mod.set_content_status(
        "case", case, "hidden", actor_id=sweeper["id"], actor_is_bot=True, conn=db
    )
    db.commit()

    as_admin.post(f"/api/admin/content/case/{case}/status", json={"status": "published"})

    trail = as_admin.get(f"/api/admin/history/case/{case}").get_json()["history"]

    assert trail[0]["action"] == "override"
    assert trail[0]["previous_status"] == "hidden"
    assert trail[0]["new_status"] == "published"
    assert trail[0]["actor_is_bot"] is False
    assert trail[0]["actor"]["id"] == admin["id"]
    assert trail[1]["actor_is_bot"] is True


@pytest.mark.parametrize(
    ("path", "payload", "status", "why"),
    [
        ("/api/admin/content/case/1/status", {"status": "deleted"}, 400, "not a real status"),
        ("/api/admin/content/post/1/status", {"status": "hidden"}, 400, "not a real target"),
        ("/api/admin/content/case/1/status", {}, 400, "no status at all"),
        ("/api/admin/content/case/999999/status", {"status": "hidden"}, 404, "no such case"),
    ],
    ids=["bad-status", "bad-type", "no-status", "missing"],
)
def test_a_malformed_override_is_refused(as_admin, path, payload, status, why):
    assert as_admin.post(path, json=payload).status_code == status, why


def test_the_history_endpoint_rejects_a_target_type_it_does_not_know(as_admin):
    assert as_admin.get("/api/admin/history/post/1").status_code == 400
    assert as_admin.get("/api/admin/history/user/1").status_code == 200
    assert as_admin.get("/api/admin/history/case/999999").get_json()["history"] == []


# --- resolving a report -----------------------------------------------------


def test_resolving_as_hidden_hides_the_content_too(as_admin, db, case, reporter):
    """`admin_resolve`, not `resolve_report` - the decision has to be carried
    out, not merely recorded."""
    _, report_id = mod.report("case", case, reporter["id"], "abuse", conn=db)
    db.commit()

    response = as_admin.post(
        f"/api/admin/reports/{report_id}/resolve",
        json={"decision": "resolved_hidden", "note": "אושר"},
    )

    assert response.status_code == 200
    assert _status(db, case) == "hidden"
    assert db.query_value("SELECT status FROM reports WHERE id = %s", (report_id,)) == mod.RESOLVED_HIDDEN


def test_resolving_as_banned_also_suspends_the_author(
    as_admin, db, case, author, reporter
):
    _, report_id = mod.report("case", case, reporter["id"], "harassment", conn=db)
    db.commit()

    as_admin.post(
        f"/api/admin/reports/{report_id}/resolve", json={"decision": "resolved_banned"}
    )

    assert db.query_value("SELECT status FROM users WHERE id = %s", (author["id"],)) == "banned"
    assert _status(db, case) == "hidden"


def test_an_admin_cannot_ban_themselves_through_the_queue(
    as_admin, db, admin, reporter, make_case
):
    """There is no way back in: the ban revokes their sessions and every
    /admin route needs one."""
    own_case = make_case(admin["id"])
    _, report_id = mod.report("case", own_case, reporter["id"], "abuse", conn=db)
    db.commit()

    response = as_admin.post(
        f"/api/admin/reports/{report_id}/resolve", json={"decision": "resolved_banned"}
    )

    assert response.status_code == 400
    assert db.query_value("SELECT status FROM users WHERE id = %s", (admin["id"],)) == "active"


def test_resolving_a_report_twice_is_a_409(as_admin, db, case, reporter):
    _, report_id = mod.report("case", case, reporter["id"], "abuse", conn=db)
    db.commit()

    first = as_admin.post(
        f"/api/admin/reports/{report_id}/resolve", json={"decision": "resolved_dismissed"}
    )
    second = as_admin.post(
        f"/api/admin/reports/{report_id}/resolve", json={"decision": "resolved_dismissed"}
    )

    assert first.status_code == 200
    assert second.status_code == 409


def test_an_unknown_decision_or_a_missing_report_is_refused(as_admin):
    assert as_admin.post(
        "/api/admin/reports/1/resolve", json={"decision": "resolved_deleted"}
    ).status_code == 400
    assert as_admin.post(
        "/api/admin/reports/999999/resolve", json={"decision": "resolved_dismissed"}
    ).status_code == 404


# --- bans -------------------------------------------------------------------


def test_an_admin_can_ban_and_unban_an_account(as_admin, db, author):
    banned = as_admin.post(f"/api/admin/users/{author['id']}/ban", json={"reason": "הטרדה"})

    assert banned.get_json() == {"ok": True, "changed": True}
    assert db.query_value("SELECT status FROM users WHERE id = %s", (author["id"],)) == "banned"

    restored = as_admin.post(f"/api/admin/users/{author['id']}/unban", json={})

    assert restored.get_json() == {"ok": True, "changed": True}
    assert db.query_value("SELECT status FROM users WHERE id = %s", (author["id"],)) == "active"


def test_banning_twice_reports_that_nothing_changed(as_admin, author):
    as_admin.post(f"/api/admin/users/{author['id']}/ban", json={})

    again = as_admin.post(f"/api/admin/users/{author['id']}/ban", json={})

    assert again.status_code == 200
    assert again.get_json()["changed"] is False


def test_an_admin_cannot_ban_themselves_directly_either(as_admin, db, admin):
    response = as_admin.post(f"/api/admin/users/{admin['id']}/ban", json={})

    assert response.status_code == 400
    assert db.query_value("SELECT status FROM users WHERE id = %s", (admin["id"],)) == "active"


def test_banning_somebody_who_does_not_exist_is_a_404(as_admin):
    assert as_admin.post("/api/admin/users/999999/ban", json={}).status_code == 404
    assert as_admin.post("/api/admin/users/999999/unban", json={}).status_code == 404


def test_suspended_accounts_are_listed_so_a_ban_can_be_undone(as_admin, db, author):
    """`GET /users` only ever returns active accounts.

    Without this list the unban endpoint existed and there was no way to find
    anybody to point it at - a ban was effectively irreversible through the UI.
    """
    assert as_admin.get("/api/admin/users/banned").get_json()["total"] == 0

    as_admin.post(f"/api/admin/users/{author['id']}/ban", json={})

    listed = as_admin.get("/api/admin/users/banned").get_json()
    assert listed["total"] == 1
    assert [user["id"] for user in listed["users"]] == [author["id"]]

    # And they really are invisible to the ordinary directory.
    assert author["id"] not in {
        user["id"] for user in as_admin.get("/api/users").get_json()["users"]
    }


def test_the_banned_list_can_be_searched(as_admin, author, make_user):
    second = make_user("שם אחר לגמרי", "other@lolsuit.test")
    for user in (author, second):
        as_admin.post(f"/api/admin/users/{user['id']}/ban", json={})

    found = as_admin.get("/api/admin/users/banned?search=הכותב").get_json()

    assert [user["id"] for user in found["users"]] == [author["id"]]
    assert found["total"] == 1
