# -*- coding: utf-8 -*-
"""The authentication endpoints, through the real Flask app and real MySQL.

This replaces `test_auth_flow.py`. Every scenario in that file was still worth
testing; its harness was a SQLite mirror of a schema three renames out of date,
and its one application import (`app.utils.verify_password`) had moved to
`app.security`.

The property this file exists for is the one a narrower test cannot see:
**`/api/auth/password-reset/request` must answer identically to everybody**.
Registered, unregistered, banned, malformed - four different journeys through
the endpoint, one indistinguishable answer, or the endpoint becomes a way to
ask "is this person a member of a Hebrew lawsuit-satire site". The assertion is
therefore written as a comparison between the four responses rather than
against a literal, because a literal would still pass if all four changed
together in a way that reintroduced a difference elsewhere.

Mail is captured rather than sent. The repo's real .env carries live SMTP
credentials, and conftest forces MAIL_BACKEND=console for exactly that reason -
this goes one further and never reaches a backend at all, so the test can
assert on what *would* have gone out.
"""

from __future__ import annotations

import pytest

from app import mail, security
from app.services import auth_service, users_service

pytestmark = pytest.mark.integration

SIGNUP = {
    "name": "אביגיל נתבעת",
    "email": "Avigail@LolSuit.test",
    "password": "correct-horse-battery",
}


@pytest.fixture
def outbox(monkeypatch):
    """Every message the app tries to send, in order.

    Patched at `app.mail` rather than at the blueprint, because that is the
    module `app/api/auth.py` holds a reference to - and because a background
    thread would otherwise race the assertion.
    """
    sent: list[dict] = []
    monkeypatch.setattr(
        mail,
        "send_mail_async",
        lambda to, subject, body, html=None: sent.append(
            {"to": to, "subject": subject, "body": body, "html": html}
        ),
    )
    return sent


def _cookie(client):
    return client.get_cookie(security.COOKIE_NAME)


# --- signing up -------------------------------------------------------------


def test_signup_stores_a_hash_signs_you_in_and_never_echoes_the_password(client, db):
    """One test for the three things signup must get right at once.

    The password must not survive as plaintext anywhere - not in the row, not
    in the response - and the caller must come out of it signed in, because a
    signup that returned 201 and no session would leave the user staring at a
    login form.
    """
    response = client.post("/api/auth/signup", json=SIGNUP)

    assert response.status_code == 201
    user = response.get_json()["user"]
    assert "password" not in user
    assert "password_hash" not in user
    assert user["email"] == SIGNUP["email"].lower()

    row = users_service.get_by_email(SIGNUP["email"].lower(), conn=db)
    assert row["password_hash"] != SIGNUP["password"]
    assert security.verify_password(SIGNUP["password"], row["password_hash"])

    assert _cookie(client) is not None
    assert client.get("/api/auth/me").get_json()["user"]["id"] == user["id"]


def test_the_address_is_stored_folded_so_one_person_cannot_hold_two_accounts(client, db):
    """Addresses are case-insensitive in practice, and the UNIQUE index is not.

    Without folding at the edge, `Avigail@` and `avigail@` are two rows to
    MySQL and one mailbox to the world - and the second signup would succeed
    while the password reset for it went to the first.
    """
    client.post("/api/auth/signup", json=SIGNUP)

    duplicate = client.post(
        "/api/auth/signup", json={**SIGNUP, "email": SIGNUP["email"].upper()}
    )

    assert duplicate.status_code == 409
    assert duplicate.get_json()["code"] == "conflict"
    assert db.query_value(
        "SELECT COUNT(*) FROM users WHERE email = %s", (SIGNUP["email"].lower(),)
    ) == 1


@pytest.mark.parametrize(
    ("payload", "why"),
    [
        ({**SIGNUP, "password": "short"}, "password below the minimum"),
        ({**SIGNUP, "password": "א" * 40}, "password over 72 bytes"),
        ({**SIGNUP, "email": "not-an-address"}, "malformed email"),
        ({**SIGNUP, "name": "א"}, "name below the minimum"),
        ({}, "nothing at all"),
    ],
    ids=["short-password", "overlong-password", "bad-email", "short-name", "empty"],
)
def test_a_rejected_signup_persists_nothing(client, db, payload, why):
    """400, and no half-made account left behind.

    The overlong-password case is the one that matters most: it is 40 Hebrew
    characters, which is 80 bytes, and reaching bcrypt with it is a 500 rather
    than a 400 under bcrypt 5.
    """
    before = db.query_value("SELECT COUNT(*) FROM users")

    response = client.post("/api/auth/signup", json=payload)

    assert response.status_code == 400, why
    assert db.query_value("SELECT COUNT(*) FROM users") == before


def test_a_body_that_is_not_json_at_all_is_a_hebrew_400_not_a_werkzeug_415(client):
    """`body_of` uses silent=True so the app answers in its own voice.

    Werkzeug's default is a 415 with an English message, which would be the one
    error in the application a Hebrew-speaking user could not read.
    """
    response = client.post(
        "/api/auth/signup", data="not json", content_type="application/json"
    )

    assert response.status_code == 400
    assert response.get_json()["code"] == "invalid"


# --- signing in -------------------------------------------------------------


def test_login_succeeds_and_issues_a_second_independent_session(app, make_user):
    """Signing in on a phone must not sign you out on a laptop.

    The previous schema kept one session row per user and upserted on login,
    which made this impossible to express - and made "revoke every session",
    which a ban and a password reset both need, impossible too.
    """
    user = make_user("אביגיל", "avigail@lolsuit.test")

    laptop, phone = app.test_client(), app.test_client()
    for browser in (laptop, phone):
        response = browser.post(
            "/api/auth/login", json={"email": user["email"], "password": user["password"]}
        )
        assert response.status_code == 200

    assert laptop.get("/api/auth/me").get_json()["user"] is not None
    assert phone.get("/api/auth/me").get_json()["user"] is not None
    assert _cookie(laptop).value != _cookie(phone).value


def test_an_unknown_address_and_a_wrong_password_are_the_same_answer(client, make_user):
    """Otherwise login is a membership oracle.

    Same status, same code, same message - asserted by comparing the two
    responses to each other, so they cannot drift apart one at a time.
    """
    user = make_user("אביגיל", "avigail@lolsuit.test")

    wrong_password = client.post(
        "/api/auth/login", json={"email": user["email"], "password": "not-it"}
    )
    unknown_address = client.post(
        "/api/auth/login", json={"email": "nobody@lolsuit.test", "password": "not-it"}
    )

    assert wrong_password.status_code == unknown_address.status_code == 401
    assert wrong_password.get_json() == unknown_address.get_json()
    assert _cookie(client) is None


def test_a_banned_account_is_told_so_rather_than_being_told_it_does_not_exist(
    client, make_user
):
    """The one place the generic answer is deliberately abandoned.

    A banned user already knows they have an account; telling them "wrong
    password" would leave them resetting a password that was never the problem.
    They authenticated correctly, so this is 403, not 401.
    """
    banned = make_user("מושעה", "banned@lolsuit.test", status="banned")

    response = client.post(
        "/api/auth/login", json={"email": banned["email"], "password": banned["password"]}
    )

    assert response.status_code == 403
    assert response.get_json()["code"] == "forbidden"


def test_a_ban_takes_effect_on_the_very_next_request_of_an_open_session(
    client, db, make_user, signed_in
):
    """`resolve_session` joins on `users.status = 'active'`, so it bites at once.

    Revoking the session rows is belt and braces; this is the guarantee. A ban
    that only took effect at the next login would leave an abusive account
    running until it happened to sign out.
    """
    user = make_user("מושעה בקרוב", "soon@lolsuit.test")
    signed_in(user)
    assert client.get("/api/auth/me").get_json()["user"] is not None

    db.execute("UPDATE users SET status = 'banned' WHERE id = %s", (user["id"],))
    db.commit()

    response = client.get("/api/users/me/memories")
    assert response.status_code == 401


# --- signing out ------------------------------------------------------------


def test_logout_destroys_the_session_server_side_not_just_in_the_browser(
    app, db, make_user
):
    """A cookie thrown away by one browser must not stay valid elsewhere.

    Replaying the captured token through a fresh client is what proves the row
    is gone rather than merely unreferenced.
    """
    user = make_user("אביגיל", "avigail@lolsuit.test")
    browser = app.test_client()
    browser.post(
        "/api/auth/login", json={"email": user["email"], "password": user["password"]}
    )
    raw_token = _cookie(browser).value
    assert db.query_value("SELECT COUNT(*) FROM sessions WHERE user_id = %s", (user["id"],)) == 1

    browser.post("/api/auth/logout")

    assert db.query_value("SELECT COUNT(*) FROM sessions WHERE user_id = %s", (user["id"],)) == 0

    replay = app.test_client()
    replay.set_cookie(security.COOKIE_NAME, raw_token)
    assert replay.get("/api/auth/me").get_json()["user"] is None


def test_logging_out_when_you_were_never_in_is_not_an_error(client):
    """Reporting one would only strand the browser's cookie.

    A 401 here is the worst possible answer: the client concludes the logout
    failed and keeps the dead cookie, so every subsequent request pays for a
    lookup that cannot succeed.
    """
    response = client.post("/api/auth/logout")

    assert response.status_code == 200
    assert response.get_json() == {"ok": True}
    assert "Max-Age=0" in response.headers["Set-Cookie"]


def test_an_expired_session_is_answered_with_an_instruction_to_drop_the_cookie(
    client, db, make_user, signed_in
):
    """401 plus Set-Cookie, because the browser is holding something worthless.

    Leaving it there would make the user look signed in to themselves while
    every request failed.
    """
    user = make_user("אביגיל", "avigail@lolsuit.test")
    signed_in(user)
    db.execute(
        "UPDATE sessions SET expires_at = DATE_SUB(UTC_TIMESTAMP(), INTERVAL 1 DAY) "
        "WHERE user_id = %s",
        (user["id"],),
    )
    db.commit()

    response = client.get("/api/users/me/memories")

    assert response.status_code == 401
    assert "Max-Age=0" in response.headers["Set-Cookie"]


def test_auth_me_answers_anonymous_without_calling_it_an_error(client):
    """The front end calls this on load to decide what to render.

    A 401 would be indistinguishable from a broken API to the code that has to
    tell "not signed in" from "server down".
    """
    response = client.get("/api/auth/me")

    assert response.status_code == 200
    assert response.get_json() == {"user": None}


# --- the password reset, and its silence ------------------------------------


def test_the_reset_request_answers_identically_to_everyone(client, db, make_user, outbox):
    """The property the endpoint exists to have.

    Four journeys - registered, unknown, banned, not an address at all - and
    one answer. Compared to each other rather than to a literal, because a
    literal only pins the text and the whole point is that the four cannot be
    told apart.
    """
    known = make_user("רשומה", "known@lolsuit.test")
    banned = make_user("מושעה", "banned@lolsuit.test", status="banned")

    answers = [
        client.post("/api/auth/password-reset/request", json={"email": known["email"]}),
        client.post("/api/auth/password-reset/request", json={"email": "nobody@lolsuit.test"}),
        client.post("/api/auth/password-reset/request", json={"email": banned["email"]}),
        client.post("/api/auth/password-reset/request", json={"email": "not-an-address"}),
        client.post("/api/auth/password-reset/request", json={}),
    ]

    first = answers[0]
    for answer in answers[1:]:
        assert answer.status_code == first.status_code == 200
        assert answer.get_json() == first.get_json()

    # Identical on the wire, and correctly different underneath: exactly one
    # link was minted, and it was the registered account's.
    assert [message["to"] for message in outbox] == [known["email"]]
    assert db.query_value("SELECT COUNT(*) FROM password_resets") == 1
    assert db.query_value("SELECT user_id FROM password_resets") == known["id"]


def test_a_banned_account_is_sent_no_reset_link_at_all(client, db, make_user, outbox):
    """Silence, not just a generic answer.

    Minting a link for a banned account would let a ban be waited out: reset
    the password, and the ban is still there but the audit trail now shows a
    successful credential change on a suspended account.
    """
    banned = make_user("מושעה", "banned@lolsuit.test", status="banned")

    client.post("/api/auth/password-reset/request", json={"email": banned["email"]})

    assert outbox == []
    assert db.query_value("SELECT COUNT(*) FROM password_resets") == 0


def test_a_second_request_inside_the_cooldown_sends_nothing_and_still_says_yes(
    client, db, make_user, outbox, monkeypatch
):
    """The rate limit must not become the oracle the rest of the endpoint isn't.

    A "slow down" response here would say "this address is registered" in the
    one case the endpoint most needs to stay quiet about.
    """
    monkeypatch.setenv("RESET_COOLDOWN_SECONDS", "3600")
    user = make_user("רשומה", "known@lolsuit.test")

    first = client.post("/api/auth/password-reset/request", json={"email": user["email"]})
    second = client.post("/api/auth/password-reset/request", json={"email": user["email"]})

    assert second.get_json() == first.get_json()
    assert second.status_code == first.status_code == 200
    assert len(outbox) == 1
    assert db.query_value("SELECT COUNT(*) FROM password_resets") == 1


def test_the_emailed_link_carries_a_token_that_is_not_the_one_in_the_database(
    client, db, make_user, outbox
):
    """Only the SHA-256 is stored, so a leaked table is not a set of live links.

    The raw value exists in exactly one place - the email - which is the same
    design the session cookie uses.
    """
    user = make_user("רשומה", "known@lolsuit.test")

    client.post("/api/auth/password-reset/request", json={"email": user["email"]})

    raw_token = outbox[0]["body"].split("token=")[1].split()[0].strip()
    stored = db.query_value("SELECT token_hash FROM password_resets")

    assert raw_token not in stored
    assert stored == auth_service.hash_token(raw_token)
    assert raw_token in outbox[0]["html"]


def test_spending_the_link_changes_the_password_and_signs_out_every_device(
    app, db, make_user, outbox, client
):
    """One transaction, three effects, and the third is the point.

    The person asking for a reset may be locked out *because* somebody else is
    signed in as them, so leaving those sessions alive would hand the account
    straight back.
    """
    user = make_user("רשומה", "known@lolsuit.test")
    laptop, phone = app.test_client(), app.test_client()
    for browser in (laptop, phone):
        browser.post(
            "/api/auth/login", json={"email": user["email"], "password": user["password"]}
        )
    assert db.query_value("SELECT COUNT(*) FROM sessions WHERE user_id = %s", (user["id"],)) == 2

    client.post("/api/auth/password-reset/request", json={"email": user["email"]})
    raw_token = outbox[0]["body"].split("token=")[1].split()[0].strip()

    response = client.post(
        "/api/auth/password-reset/confirm",
        json={"token": raw_token, "password": "brand-new-passphrase"},
    )

    assert response.status_code == 200
    assert db.query_value("SELECT COUNT(*) FROM sessions WHERE user_id = %s", (user["id"],)) == 0
    assert laptop.get("/api/auth/me").get_json()["user"] is None
    assert phone.get("/api/auth/me").get_json()["user"] is None

    fresh = app.test_client()
    assert (
        fresh.post(
            "/api/auth/login",
            json={"email": user["email"], "password": "brand-new-passphrase"},
        ).status_code
        == 200
    )


def test_a_reset_link_works_exactly_once(client, make_user, outbox):
    """The guarantee is a guarded UPDATE, not a SELECT then a write.

    `used_at IS NULL` is in the WHERE clause, so two requests arriving together
    are decided by the database and the loser sees rowcount 0.
    """
    user = make_user("רשומה", "known@lolsuit.test")
    client.post("/api/auth/password-reset/request", json={"email": user["email"]})
    raw_token = outbox[0]["body"].split("token=")[1].split()[0].strip()

    first = client.post(
        "/api/auth/password-reset/confirm", json={"token": raw_token, "password": "first-attempt-x"}
    )
    second = client.post(
        "/api/auth/password-reset/confirm", json={"token": raw_token, "password": "second-attempt"}
    )

    assert first.status_code == 200
    assert second.status_code == 400
    assert second.get_json()["code"] == "invalid"


def test_an_expired_link_is_refused_with_the_same_message_as_a_forged_one(
    client, db, make_user, outbox
):
    """Expired, spent and invented all answer alike.

    Distinguishing them would confirm that a token was once real, which is
    enough to tell an attacker their guess was close.
    """
    user = make_user("רשומה", "known@lolsuit.test")
    client.post("/api/auth/password-reset/request", json={"email": user["email"]})
    raw_token = outbox[0]["body"].split("token=")[1].split()[0].strip()

    db.execute(
        "UPDATE password_resets SET expires_at = DATE_SUB(UTC_TIMESTAMP(), INTERVAL 1 MINUTE)"
    )
    db.commit()

    expired = client.post(
        "/api/auth/password-reset/confirm", json={"token": raw_token, "password": "new-passphrase"}
    )
    forged = client.post(
        "/api/auth/password-reset/confirm",
        json={"token": "never-existed", "password": "new-passphrase"},
    )

    assert expired.status_code == forged.status_code == 400
    assert expired.get_json() == forged.get_json()


def test_asking_for_a_new_link_burns_the_previous_one(client, db, make_user, outbox, monkeypatch):
    """A leaked earlier email must stop working the moment a new one is asked for.

    Both happen in one transaction, so a crash between them cannot leave two
    live links.
    """
    monkeypatch.setenv("RESET_COOLDOWN_SECONDS", "0")
    user = make_user("רשומה", "known@lolsuit.test")

    client.post("/api/auth/password-reset/request", json={"email": user["email"]})
    client.post("/api/auth/password-reset/request", json={"email": user["email"]})
    first_token = outbox[0]["body"].split("token=")[1].split()[0].strip()
    second_token = outbox[1]["body"].split("token=")[1].split()[0].strip()
    assert first_token != second_token

    stale = client.post(
        "/api/auth/password-reset/confirm", json={"token": first_token, "password": "new-passphrase"}
    )
    current = client.post(
        "/api/auth/password-reset/confirm",
        json={"token": second_token, "password": "new-passphrase"},
    )

    assert stale.status_code == 400
    assert current.status_code == 200


@pytest.mark.parametrize(
    ("payload", "why"),
    [
        ({"password": "long-enough-x"}, "no token"),
        ({"token": "something", "password": "short"}, "password below the minimum"),
        ({"token": "", "password": "long-enough-x"}, "empty token"),
    ],
    ids=["no-token", "short-password", "empty-token"],
)
def test_the_confirm_endpoint_validates_before_it_touches_the_token(client, payload, why):
    """Both fields are checked before anything is spent.

    A short password that consumed the token first would burn the user's only
    link and then refuse them, with nothing left to retry with.
    """
    assert client.post("/api/auth/password-reset/confirm", json=payload).status_code == 400, why


# --- checking a link without spending it ------------------------------------
#
# The page behind a reset link asks this on load so it can show the form or the
# expired notice. Everything below is one property in four parts: it must
# answer, it must not spend, and it must not say more than the confirm endpoint
# already says.


def _link_for(client, outbox, user) -> str:
    """Request a reset for this user and pull the raw token out of the email."""
    client.post("/api/auth/password-reset/request", json={"email": user["email"]})
    return outbox[-1]["body"].split("token=")[1].split()[0].strip()


def test_validating_a_link_does_not_spend_it(client, db, make_user, outbox):
    """The reason the endpoint is a GET and not a second confirm.

    A check that consumed the token would mean the reset page destroyed the
    very link it was opened with, and the form it then rendered could never
    succeed. Looked at twice, and still spendable afterwards.
    """
    user = make_user("רשומה", "known@lolsuit.test")
    raw_token = _link_for(client, outbox, user)

    first = client.get(f"/api/auth/password-reset/validate?token={raw_token}")
    second = client.get(f"/api/auth/password-reset/validate?token={raw_token}")

    assert first.status_code == second.status_code == 200
    assert db.query_value("SELECT used_at FROM password_resets") is None

    spent = client.post(
        "/api/auth/password-reset/confirm",
        json={"token": raw_token, "password": "new-passphrase"},
    )

    assert spent.status_code == 200
    assert db.query_value("SELECT used_at FROM password_resets") is not None


def test_an_expired_link_does_not_validate(client, db, make_user, outbox):
    """The bug this whole endpoint exists for: 30 minutes later, no form."""
    user = make_user("רשומה", "known@lolsuit.test")
    raw_token = _link_for(client, outbox, user)

    db.execute(
        "UPDATE password_resets SET expires_at = DATE_SUB(UTC_TIMESTAMP(), INTERVAL 1 MINUTE)"
    )
    db.commit()

    assert client.get(f"/api/auth/password-reset/validate?token={raw_token}").status_code == 400


def test_a_spent_link_does_not_validate(client, make_user, outbox):
    """Single use is single use, including for the check.

    Someone who resets their password and then reopens the email must be told
    the link is gone rather than shown a form that will refuse them.
    """
    user = make_user("רשומה", "known@lolsuit.test")
    raw_token = _link_for(client, outbox, user)

    client.post(
        "/api/auth/password-reset/confirm",
        json={"token": raw_token, "password": "new-passphrase"},
    )

    assert client.get(f"/api/auth/password-reset/validate?token={raw_token}").status_code == 400


def test_validate_answers_alike_for_expired_forged_and_missing(
    client, db, make_user, outbox
):
    """Four refusals compared to each other rather than to a literal.

    A check endpoint is a cheaper oracle than confirm - no password needed - so
    it has to be at least as silent. Expired, spent, invented and absent are one
    answer, and the answer to a live link carries nothing about whose it is.
    """
    user = make_user("רשומה", "known@lolsuit.test")
    expired_token = _link_for(client, outbox, user)
    db.execute(
        "UPDATE password_resets SET expires_at = DATE_SUB(UTC_TIMESTAMP(), INTERVAL 1 MINUTE)"
    )
    db.commit()

    refusals = [
        client.get(f"/api/auth/password-reset/validate?token={expired_token}"),
        client.get("/api/auth/password-reset/validate?token=never-existed"),
        client.get("/api/auth/password-reset/validate?token="),
        client.get("/api/auth/password-reset/validate"),
    ]

    first = refusals[0]
    for refusal in refusals[1:]:
        assert refusal.status_code == first.status_code == 400
        assert refusal.get_json() == first.get_json()

    live = make_user("שנייה", "second@lolsuit.test")
    accepted = client.get(f"/api/auth/password-reset/validate?token={_link_for(client, outbox, live)}")

    assert accepted.get_json() == {"ok": True}
