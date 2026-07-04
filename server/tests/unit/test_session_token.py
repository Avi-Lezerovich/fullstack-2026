"""Unit tests — session-token extraction from the cookie.

Target under test: server/app/utils.py -> get_session_token(). It reads and
sanitizes the `session_id` cookie, and it is the front door of every
authenticated request, so its edge cases (no cookie, empty cookie) matter.

The function needs a Flask *request context* to run, but a bare in-process one —
no app config, no routes, no database, no network — so these remain fast,
isolated unit tests (F.I.R.S.T. holds).
"""
import pytest
from flask import Flask

from app.utils import get_session_token

_app = Flask(__name__)


@pytest.mark.unit
def test_get_session_token_returns_none_without_a_cookie():
    # Arrange — a request that carries no cookies at all (anonymous visitor).
    with _app.test_request_context("/"):
        # Act
        token = get_session_token()

    # Assert — no cookie means no token, not a crash.
    assert token is None


@pytest.mark.unit
def test_get_session_token_returns_none_for_empty_cookie_value():
    # Arrange — the cookie exists but its value is empty (e.g. right after logout
    # cleared it, or a broken client).
    with _app.test_request_context("/", headers={"Cookie": "session_id="}):
        # Act
        token = get_session_token()

    # Assert — an empty value is treated as "not logged in".
    assert token is None


@pytest.mark.unit
def test_get_session_token_returns_the_cookie_value():
    # Arrange — a normal request carrying a session cookie.
    with _app.test_request_context("/", headers={"Cookie": "session_id=abc123"}):
        # Act
        token = get_session_token()

    # Assert — the raw token comes back for the session lookup.
    assert token == "abc123"
