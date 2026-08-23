"""Passwords, session tokens, cookies and the authorisation decorators.

Two decisions worth naming:

**Sessions are server-side rows, and there may be many per user.** The previous
version kept one row per user and upserted on login, which cannot express
"revoke every session" - something both a ban and a password reset must do.

**Only the hash of a session token is stored.** The cookie carries the raw
value; the database holds its SHA-256. Reading the sessions table therefore
does not hand an attacker a set of live sessions. SHA-256 (not bcrypt) is the
right choice here: the token is 32 bytes of `secrets` output, so there is no
low-entropy guess to slow down, and this runs on every single request.
"""

from __future__ import annotations

import functools
from typing import Any, Callable

import bcrypt
from flask import g, request

from .config import Settings, get_settings
from .db import Db
from .errors import fail
from .services import auth_service

# Re-exported for convenience; auth_service owns them because it owns the
# tables they are written to.
mint_token = auth_service.mint_token
hash_token = auth_service.hash_token

COOKIE_NAME = "session_id"

# bcrypt refuses to hash anything longer than this. Version 5 raises rather
# than silently truncating, so the limit has to be enforced before we get here.
MAX_PASSWORD_BYTES = 72
MIN_PASSWORD_LENGTH = 8


# --- passwords --------------------------------------------------------------


def hash_password(password: str) -> str:
    rounds = get_settings().bcrypt_rounds
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=rounds)).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        # Malformed or truncated hash in the database - treat as a failed
        # login rather than a 500.
        return False


def password_problem(password: str) -> str | None:
    """Hebrew description of why a password is unacceptable, or None."""
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"הסיסמה חייבת להכיל לפחות {MIN_PASSWORD_LENGTH} תווים."
    if len(password.encode("utf-8")) > MAX_PASSWORD_BYTES:
        return "הסיסמה ארוכה מדי."
    return None


# --- session tokens ---------------------------------------------------------


def cookie_flags(settings: Settings | None = None) -> tuple[str, bool]:
    """(SameSite, Secure).

    A cross-site front end over HTTPS needs SameSite=None, which browsers only
    honour together with Secure. Over plain HTTP in development that pair would
    make the cookie be dropped entirely, so Lax is used instead.
    """
    s = settings or get_settings()
    return ("None", True) if s.session_secure else ("Lax", False)


def set_session_cookie(response, raw_token: str, settings: Settings | None = None):
    s = settings or get_settings()
    samesite, secure = cookie_flags(s)
    response.set_cookie(
        COOKIE_NAME,
        raw_token,
        httponly=True,  # unreadable from JavaScript
        samesite=samesite,
        secure=secure,
        path="/",
        max_age=s.session_ttl_days * 24 * 60 * 60,
    )
    return response


def clear_session_cookie(response, settings: Settings | None = None):
    samesite, secure = cookie_flags(settings)
    response.set_cookie(
        COOKIE_NAME, "", httponly=True, samesite=samesite, secure=secure, path="/", max_age=0
    )
    return response


# --- request authentication -------------------------------------------------


def _load_user(conn: Db | None = None) -> dict[str, Any] | None:
    """Resolve the request's cookie to a user, or None.

    Cached on `g` so several decorators and a route body all share one lookup.
    """
    if "auth_user" in g:
        return g.auth_user

    raw_token = request.cookies.get(COOKIE_NAME)
    user = auth_service.resolve_session(raw_token, conn=conn) if raw_token else None
    g.auth_user = user
    return user


def current_user() -> dict[str, Any] | None:
    return _load_user()


def _unauthorised():
    """401 plus an instruction to drop the cookie.

    Sent when a session is expired, revoked, or belongs to a banned account -
    in every case the browser is holding something worthless, and leaving it
    there would make the user look logged in.
    """
    response, status = fail("unauthorized")
    return clear_session_cookie(response), status


def require_auth(view: Callable) -> Callable:
    """Reject anonymous requests. Sets g.user and g.user_id."""

    @functools.wraps(view)
    def wrapper(*args, **kwargs):
        user = _load_user()
        if user is None:
            return _unauthorised()
        g.user = user
        g.user_id = user["id"]
        return view(*args, **kwargs)

    return wrapper


def require_admin(view: Callable) -> Callable:
    """Human moderators only. Distinct from the moderator *bots*, which never
    make HTTP requests at all."""

    @functools.wraps(view)
    def wrapper(*args, **kwargs):
        user = _load_user()
        if user is None:
            return _unauthorised()
        if not user.get("is_admin"):
            return fail("forbidden", "הפעולה הזו מיועדת למנהלי המערכת בלבד.")
        g.user = user
        g.user_id = user["id"]
        return view(*args, **kwargs)

    return wrapper


def optional_auth(view: Callable) -> Callable:
    """For endpoints that show more to a signed-in viewer but work anonymously
    (the feed marks which cases you have already liked)."""

    @functools.wraps(view)
    def wrapper(*args, **kwargs):
        user = _load_user()
        g.user = user
        g.user_id = user["id"] if user else None
        return view(*args, **kwargs)

    return wrapper
