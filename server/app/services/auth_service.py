"""Sessions and password-reset tokens.

Both are the same shape: a high-entropy random string handed to exactly one
person, stored only as a SHA-256 digest, with an expiry the database checks.
Token minting and hashing live here rather than in app.security because this
module owns the tables they are written to (and it keeps app.security free to
import this one without a cycle).
"""

from __future__ import annotations

import hashlib
import secrets
from typing import Any

from ..db import Db, owned

# How stale last_seen_at is allowed to get before we write it again. Without
# this, every authenticated GET - including each SSE reconnect - would take a
# row lock on the sessions table.
_LAST_SEEN_REFRESH_MINUTES = 5


def mint_token() -> str:
    """32 bytes from the OS CSPRNG, URL-safe."""
    return secrets.token_urlsafe(32)


def hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


# --- sessions ---------------------------------------------------------------


def create_session(user_id: int, ttl_days: int = 7, conn: Db | None = None) -> str:
    """Start a session and return the RAW token, which is never stored.

    Several sessions per user is intentional: signing in on a phone must not
    sign you out on a laptop, and "revoke everything" has to be expressible.
    """
    raw = mint_token()
    with owned(conn) as db:
        db.execute(
            "INSERT INTO sessions (user_id, token_hash, created_at, expires_at, last_seen_at) "
            "VALUES (%s, %s, UTC_TIMESTAMP(), "
            "        DATE_ADD(UTC_TIMESTAMP(), INTERVAL %s DAY), UTC_TIMESTAMP())",
            (user_id, hash_token(raw), int(ttl_days)),
        )
        db.commit_if_owned()
    return raw


def resolve_session(raw_token: str | None, conn: Db | None = None) -> dict[str, Any] | None:
    """The user behind a session cookie, or None.

    None is returned for an unknown token, an expired one, and for a banned
    account. Checking the ban here is what makes a ban bite on the very next
    request: revoking the rows is best-effort, this is the guarantee.

    Expiry is evaluated by the database, so it cannot disagree with the
    UTC_TIMESTAMP() used to set it.
    """
    if not raw_token:
        return None

    token_hash = hash_token(raw_token)
    with owned(conn) as db:
        user = db.query_one(
            "SELECT u.*, s.id AS session_id "
            "FROM sessions s JOIN users u ON u.id = s.user_id "
            "WHERE s.token_hash = %s "
            "  AND s.expires_at > UTC_TIMESTAMP() "
            "  AND u.status = 'active'",
            (token_hash,),
        )
        if user is None:
            return None

        db.execute(
            "UPDATE sessions SET last_seen_at = UTC_TIMESTAMP() "
            "WHERE id = %s AND (last_seen_at IS NULL OR "
            "      last_seen_at < DATE_SUB(UTC_TIMESTAMP(), INTERVAL %s MINUTE))",
            (user["session_id"], _LAST_SEEN_REFRESH_MINUTES),
        )
        db.commit_if_owned()
        return user


def delete_session(raw_token: str | None, conn: Db | None = None) -> int:
    """Sign out one device."""
    if not raw_token:
        return 0
    with owned(conn) as db:
        result = db.execute(
            "DELETE FROM sessions WHERE token_hash = %s", (hash_token(raw_token),)
        )
        db.commit_if_owned()
        return result.rowcount


def delete_all_sessions(user_id: int, conn: Db | None = None) -> int:
    """Sign out everywhere. Used by a password reset and by a ban."""
    with owned(conn) as db:
        result = db.execute("DELETE FROM sessions WHERE user_id = %s", (user_id,))
        db.commit_if_owned()
        return result.rowcount


def count_sessions(user_id: int, conn: Db | None = None) -> int:
    with owned(conn) as db:
        return int(
            db.query_value(
                "SELECT COUNT(*) FROM sessions WHERE user_id = %s AND expires_at > UTC_TIMESTAMP()",
                (user_id,),
                default=0,
            )
        )


def purge_expired_sessions(conn: Db | None = None) -> int:
    with owned(conn) as db:
        result = db.execute("DELETE FROM sessions WHERE expires_at <= UTC_TIMESTAMP()")
        db.commit_if_owned()
        return result.rowcount


# --- password resets --------------------------------------------------------


def create_password_reset(
    user_id: int, ttl_minutes: int = 30, conn: Db | None = None
) -> str:
    """Issue a reset token and return the RAW value to be emailed."""
    raw = mint_token()
    with owned(conn) as db:
        db.execute(
            "INSERT INTO password_resets (user_id, token_hash, created_at, expires_at) "
            "VALUES (%s, %s, UTC_TIMESTAMP(), "
            "        DATE_ADD(UTC_TIMESTAMP(), INTERVAL %s MINUTE))",
            (user_id, hash_token(raw), int(ttl_minutes)),
        )
        db.commit_if_owned()
    return raw


def consume_password_reset(raw_token: str, conn: Db | None = None) -> int | None:
    """Spend a reset token exactly once. Returns the user id, or None.

    The single-use guarantee is the guarded UPDATE below, not a SELECT followed
    by a write: `used_at IS NULL` is part of the WHERE clause, so if two
    requests arrive together the database decides which one wins and the loser
    sees rowcount 0.
    """
    if not raw_token:
        return None

    token_hash = hash_token(raw_token)
    with owned(conn) as db:
        claimed = db.execute(
            "UPDATE password_resets SET used_at = UTC_TIMESTAMP() "
            "WHERE token_hash = %s "
            "  AND used_at IS NULL "
            "  AND expires_at > UTC_TIMESTAMP()",
            (token_hash,),
        )
        if claimed.rowcount != 1:
            db.commit_if_owned()
            return None

        row = db.query_one(
            "SELECT user_id FROM password_resets WHERE token_hash = %s", (token_hash,)
        )
        db.commit_if_owned()
        return int(row["user_id"]) if row else None


def invalidate_password_resets(user_id: int, conn: Db | None = None) -> int:
    """Burn any other outstanding reset links for this user."""
    with owned(conn) as db:
        result = db.execute(
            "UPDATE password_resets SET used_at = UTC_TIMESTAMP() "
            "WHERE user_id = %s AND used_at IS NULL",
            (user_id,),
        )
        db.commit_if_owned()
        return result.rowcount


def issue_password_reset(
    user_id: int, ttl_minutes: int = 30, conn: Db | None = None
) -> str:
    """Invalidate any outstanding links and mint a fresh one, atomically.

    Requesting a new link must kill the old one in the same transaction, so a
    leaked earlier email cannot be redeemed afterwards.
    """
    with owned(conn) as db:
        invalidate_password_resets(user_id, conn=db.db)
        raw = create_password_reset(user_id, ttl_minutes=ttl_minutes, conn=db.db)
        db.commit_if_owned()
        return raw


def reset_password(
    raw_token: str, password_hash: str, conn: Db | None = None
) -> tuple[str, int | None]:
    """Spend a reset token, set the new password and sign the user out
    everywhere - one transaction.

    Splitting these would allow a crash to leave a spent token beside an
    unchanged password, locking the user out with no way back in.
    """
    from . import users_service  # local import keeps the module graph acyclic

    with owned(conn) as db:
        user_id = consume_password_reset(raw_token, conn=db.db)
        if user_id is None:
            return "invalid", None

        users_service.set_password(user_id, password_hash, conn=db.db)
        # The person who asked for the reset may be locked out *because*
        # someone else is signed in as them.
        delete_all_sessions(user_id, conn=db.db)
        db.commit_if_owned()
        return "ok", user_id
