"""Integration tests — the auth flow (the pyramid middle).

Each test drives the REAL Flask endpoints through the test client, so one test
exercises several units at once: the route handler + the session-cookie helpers +
require_auth + the services layer + storage. The storage is a throwaway SQLite DB
injected by conftest, so these stay fast and hermetic while still testing the seams
between units — exactly what integration tests are for.

Every test follows Arrange -> Act -> Assert.
"""
import re
import sqlite3

import pytest

from app.utils import verify_password


def _session_token(resp) -> str:
    """Extract the raw session token from a response's Set-Cookie header."""
    for cookie in resp.headers.get_all("Set-Cookie"):
        match = re.match(r"session_id=([^;]+)", cookie)
        if match:
            return match.group(1)
    raise AssertionError("no session cookie found in the response")


def _stored_hash(db_path: str, email: str):
    """Peek directly at the DB to inspect what signup actually persisted."""
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        row = con.execute(
            "SELECT password_hash FROM users WHERE email = ?", (email,)
        ).fetchone()
        return row["password_hash"] if row else None
    finally:
        con.close()


@pytest.mark.integration
def test_signup_persists_user_with_hashed_password_and_sets_cookie(client, db_path):
    # Arrange — a brand-new registrant.
    payload = {"name": "Alice", "email": "alice@runi.ac.il", "password": "secret123"}

    # Act — hit the real signup endpoint.
    resp = client.post("/api/auth/signup", json=payload)

    # Assert — 201, the public user comes back WITHOUT any password field...
    assert resp.status_code == 201, resp.get_data(as_text=True)
    user = resp.get_json()["user"]
    assert user["email"] == "alice@runi.ac.il"
    assert "password" not in user and "password_hash" not in user

    # ...the seam that only integration catches: the password was hashed (not stored
    # as plaintext) AND the stored hash actually verifies.
    stored = _stored_hash(db_path, "alice@runi.ac.il")
    assert stored is not None
    assert stored != "secret123"
    assert verify_password("secret123", stored) is True

    # ...and a session cookie was issued (login-on-signup).
    assert any("session_id=" in c for c in resp.headers.get_all("Set-Cookie"))


def _user_count(db_path: str, email: str) -> int:
    con = sqlite3.connect(db_path)
    try:
        return con.execute(
            "SELECT COUNT(*) FROM users WHERE LOWER(email) = LOWER(?)", (email,)
        ).fetchone()[0]
    finally:
        con.close()


@pytest.mark.integration
def test_signup_rejects_duplicate_email(client, db_path):
    # Arrange — register once successfully.
    first = client.post(
        "/api/auth/signup",
        json={"name": "Alice", "email": "alice@runi.ac.il", "password": "secret123"},
    )
    assert first.status_code == 201

    # Act — try to register the same email again (different case, to prove the
    # check is case-insensitive).
    dup = client.post(
        "/api/auth/signup",
        json={"name": "Alice Two", "email": "ALICE@runi.ac.il", "password": "other123"},
    )

    # Assert — rejected with 409 Conflict, an error message, and NO second row.
    assert dup.status_code == 409
    assert "error" in dup.get_json()
    assert _user_count(db_path, "alice@runi.ac.il") == 1


@pytest.mark.integration
def test_signup_rejects_missing_fields(client, db_path):
    # Arrange — a payload with no password.
    payload = {"name": "Bob", "email": "bob@runi.ac.il"}

    # Act
    resp = client.post("/api/auth/signup", json=payload)

    # Assert — 400 Bad Request, an error message, and nothing persisted.
    assert resp.status_code == 400
    assert "error" in resp.get_json()
    assert _user_count(db_path, "bob@runi.ac.il") == 0


@pytest.mark.integration
def test_signup_rejects_overlong_password(client, db_path):
    # Arrange — a password past bcrypt's 72-byte limit (bcrypt >= 5 would raise,
    # turning this into a 500 without the route's guard).
    payload = {"name": "Bob", "email": "bob@runi.ac.il", "password": "x" * 80}

    # Act
    resp = client.post("/api/auth/signup", json=payload)

    # Assert — a clean 400 with an error message, and nothing persisted.
    assert resp.status_code == 400
    assert "error" in resp.get_json()
    assert _user_count(db_path, "bob@runi.ac.il") == 0


@pytest.mark.integration
def test_login_succeeds_with_correct_credentials(client):
    # Arrange — an existing account (created via signup).
    client.post(
        "/api/auth/signup",
        json={"name": "Alice", "email": "alice@runi.ac.il", "password": "secret123"},
    )

    # Act — log in with the correct credentials.
    resp = client.post(
        "/api/auth/login",
        json={"email": "alice@runi.ac.il", "password": "secret123"},
    )

    # Assert — 200, the public user, and a fresh session cookie.
    assert resp.status_code == 200
    assert resp.get_json()["user"]["email"] == "alice@runi.ac.il"
    assert any("session_id=" in c for c in resp.headers.get_all("Set-Cookie"))


@pytest.mark.integration
def test_login_rejects_wrong_password(client):
    # Arrange — one real account exists.
    client.post(
        "/api/auth/signup",
        json={"name": "Alice", "email": "alice@runi.ac.il", "password": "secret123"},
    )

    # Act — right user, WRONG password.
    resp = client.post(
        "/api/auth/login",
        json={"email": "alice@runi.ac.il", "password": "not-my-password"},
    )

    # Assert — 401 with a generic error message.
    assert resp.status_code == 401
    assert "error" in resp.get_json()


@pytest.mark.integration
def test_login_rejects_unknown_email(client):
    # Arrange — one real account exists, so the failure below is specifically
    # about the email being unknown, not about an empty database.
    client.post(
        "/api/auth/signup",
        json={"name": "Alice", "email": "alice@runi.ac.il", "password": "secret123"},
    )

    # Act — an email that was never registered, with a plausible password.
    resp = client.post(
        "/api/auth/login",
        json={"email": "ghost@runi.ac.il", "password": "secret123"},
    )

    # Assert — the SAME generic 401 as a wrong password (no user enumeration).
    assert resp.status_code == 401
    assert "error" in resp.get_json()


@pytest.mark.integration
def test_login_rejects_missing_fields(client):
    # Arrange — a login payload with no password (malformed request, not wrong creds).
    payload = {"email": "alice@runi.ac.il"}

    # Act
    resp = client.post("/api/auth/login", json=payload)

    # Assert — 400 Bad Request before any credential check happens.
    assert resp.status_code == 400
    assert "error" in resp.get_json()


@pytest.mark.integration
def test_logout_destroys_the_session_server_side(client):
    # Arrange — sign up (logs us in) and keep a copy of the raw session token.
    signup = client.post(
        "/api/auth/signup",
        json={"name": "Alice", "email": "alice@runi.ac.il", "password": "secret123"},
    )
    token = _session_token(signup)
    assert client.get("/api/auth/me").status_code == 200  # sanity: authenticated

    # Act — log out.
    out = client.post("/api/auth/logout")
    assert out.status_code == 200

    # Assert — the OLD token no longer works even when presented explicitly.
    # (The test client's cookie jar honors logout's delete_cookie, so a plain /me
    # would return 401 with or without the server-side delete — replaying the
    # stale token by hand is what proves the session row itself was destroyed.)
    replay = client.get("/api/auth/me", headers={"Cookie": f"session_id={token}"})
    assert replay.status_code == 401


@pytest.mark.integration
def test_logout_without_a_session_is_a_safe_noop(client):
    # Arrange — nobody is logged in (fresh client, no cookie). This is a real
    # scenario: a double-click on the logout button, or an already-expired session.

    # Act — log out anyway.
    resp = client.post("/api/auth/logout")

    # Assert — still a clean 200, never an error (logout is idempotent).
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True


@pytest.mark.integration
def test_require_auth_blocks_requests_without_a_session(client):
    # Act — hit a protected route with NO session cookie.
    resp = client.patch("/api/users/me", json={})

    # Assert — require_auth rejects the request before the handler runs.
    assert resp.status_code == 401
    assert "error" in resp.get_json()


@pytest.mark.integration
def test_require_auth_allows_requests_with_a_valid_session(client):
    # Arrange — sign up to obtain a valid session cookie (reused by the client).
    client.post(
        "/api/auth/signup",
        json={"name": "Alice", "email": "alice@runi.ac.il", "password": "secret123"},
    )

    # Act — hit the same protected route, now authenticated.
    resp = client.patch("/api/users/me", json={})

    # Assert — require_auth resolves the session and lets the request through.
    assert resp.status_code == 200
    assert resp.get_json()["user"]["email"] == "alice@runi.ac.il"
