# -*- coding: utf-8 -*-
"""The session cookie: its flags, and how a request is resolved back to a user.

Two dead files merge here. `test_session_cookie.py` imported
`app.utils.session_cookie_flags`, which is now `app.security.cookie_flags`, and
`test_session_token.py` imported `app.utils.get_session_token`, which has no
successor at all - the cookie read was inlined into `security._load_user`:

    raw_token = request.cookies.get(COOKIE_NAME)
    user = auth_service.resolve_session(raw_token, conn=conn) if raw_token else None

There is nothing left to call, but the three cases that function covered - no
cookie, an empty cookie, a cookie with a value - are still three distinct paths
through the front door of every authenticated request. They are kept below,
aimed at the seam that exists rather than at the name that does not.

The flag pair is worth a test of its own because getting it wrong fails
*silently* and only in production: SameSite=None without Secure is dropped by
the browser outright, so nobody is signed in and no error is logged anywhere.

No database: `resolve_session` is handed a fake, and the anonymous paths never
reach one.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from flask import Flask

from app import security

pytestmark = pytest.mark.unit

_app = Flask(__name__)


# --- the flags --------------------------------------------------------------


def test_plain_http_development_gets_lax_and_insecure(monkeypatch):
    """Lax, because SameSite=None here would delete the cookie.

    Browsers only honour SameSite=None together with Secure, and there is no
    Secure over http://localhost - so the "correct" cross-site pair is the one
    setting that breaks local development completely.
    """
    monkeypatch.delenv("FLASK_SESSION_SECURE", raising=False)

    assert security.cookie_flags() == ("Lax", False)


def test_a_cross_site_deployment_gets_none_and_secure(monkeypatch):
    """The pair a front end on another origin needs, and it is a pair.

    Neither half works without the other: Secure alone would not be sent
    cross-site, and None alone would be dropped.
    """
    monkeypatch.setenv("FLASK_SESSION_SECURE", "1")

    assert security.cookie_flags() == ("None", True)


def test_the_flags_can_be_taken_from_a_settings_object_instead(monkeypatch):
    """`set_session_cookie` passes the settings it already has.

    Re-reading the environment there would be a second chance for the two
    halves of one response to disagree.
    """
    monkeypatch.delenv("FLASK_SESSION_SECURE", raising=False)
    secure_settings = SimpleNamespace(session_secure=True)

    assert security.cookie_flags(secure_settings) == ("None", True)


# --- setting and clearing ---------------------------------------------------


def _set_cookie_header(monkeypatch, secure: str = "0") -> str:
    monkeypatch.setenv("FLASK_SESSION_SECURE", secure)
    with _app.test_request_context("/"):
        from flask import jsonify

        response = security.set_session_cookie(jsonify({}), "raw-token-value")
        return response.headers["Set-Cookie"]


def test_the_session_cookie_is_unreadable_from_javascript(monkeypatch):
    """HttpOnly is the reason an XSS cannot walk off with a session.

    It is also why `AuthContext` has to ask the server who is signed in rather
    than reading the cookie - the two facts are the same decision.
    """
    header = _set_cookie_header(monkeypatch)

    assert "HttpOnly" in header
    assert "raw-token-value" in header
    assert "Path=/" in header


def test_the_cookie_outlives_the_browser_session_by_the_configured_ttl(monkeypatch):
    monkeypatch.setenv("SESSION_TTL_DAYS", "3")
    header = _set_cookie_header(monkeypatch)

    assert f"Max-Age={3 * 24 * 60 * 60}" in header


def test_clearing_expires_the_cookie_rather_than_leaving_it_empty(monkeypatch):
    """Max-Age=0 is what actually removes it.

    Setting an empty value alone leaves the cookie in the jar, so the browser
    keeps sending it and every request pays for a failed lookup.
    """
    monkeypatch.setenv("FLASK_SESSION_SECURE", "0")
    with _app.test_request_context("/"):
        from flask import jsonify

        header = security.clear_session_cookie(jsonify({})).headers["Set-Cookie"]

    assert "Max-Age=0" in header
    assert "HttpOnly" in header


# --- resolving a request to a user ------------------------------------------
#
# What `get_session_token` used to cover, aimed at the code that replaced it.


def test_a_request_with_no_cookie_is_anonymous(monkeypatch):
    """And it must not cost a database lookup.

    Every anonymous page view goes through here; a query per view would be a
    connection per view for a reader who is not signed in.
    """
    called = []
    monkeypatch.setattr(
        security.auth_service, "resolve_session", lambda *a, **k: called.append(a) or None
    )

    with _app.test_request_context("/"):
        assert security.current_user() is None

    assert called == []


def test_an_empty_cookie_value_is_anonymous_too(monkeypatch):
    """A cookie the browser kept after a logout says `session_id=`.

    The falsy check is what stops that empty string being hashed and looked up
    on every single request from a signed-out browser.
    """
    called = []
    monkeypatch.setattr(
        security.auth_service, "resolve_session", lambda *a, **k: called.append(a) or None
    )

    with _app.test_request_context("/", headers={"Cookie": "session_id="}):
        assert security.current_user() is None

    assert called == []


def test_a_cookie_with_a_value_is_handed_to_the_session_lookup(monkeypatch):
    """The raw token goes through unmodified - no trimming, no decoding.

    It is compared by SHA-256 against a stored digest, so any sanitising here
    would silently stop matching the value that was minted.
    """
    seen = []

    def fake_resolve(raw_token, conn=None):
        seen.append(raw_token)
        return {"id": 7, "name": "עדי"}

    monkeypatch.setattr(security.auth_service, "resolve_session", fake_resolve)

    with _app.test_request_context("/", headers={"Cookie": "session_id=abc123"}):
        user = security.current_user()

    assert seen == ["abc123"]
    assert user["id"] == 7


def test_the_user_is_looked_up_once_however_many_times_it_is_asked_for(monkeypatch):
    """`g` caches it, and two decorators plus a route body all ask.

    Without the cache, `require_auth` on a view that also calls
    `current_user()` would take two row locks on `sessions` per request.
    """
    calls = []
    monkeypatch.setattr(
        security.auth_service,
        "resolve_session",
        lambda raw, conn=None: calls.append(raw) or {"id": 7},
    )

    with _app.test_request_context("/", headers={"Cookie": "session_id=abc123"}):
        security.current_user()
        security.current_user()
        security.current_user()

    assert len(calls) == 1
