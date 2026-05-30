"""Auth helpers: bcrypt password hashing and stateful session cookies (lecture 5)."""
import os
from functools import wraps

import bcrypt
from flask import request, jsonify, g

SESSION_COOKIE_NAME = "session_id"


def hash_password(plain: str) -> str:
    """Hash a plaintext password with bcrypt — we NEVER store plaintext (see lecture 5)."""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_password(plain: str, stored: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), stored.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def session_cookie_flags():
    """SameSite=None requires Secure in modern browsers; Lax works for same-site dev.

    In dev the browser talks to Vite (:5173) which proxies /api → Flask, so the request
    is same-origin and Lax is fine. Set FLASK_SESSION_SECURE=1 behind HTTPS.
    """
    secure = os.environ.get("FLASK_SESSION_SECURE", "").lower() in ("1", "true", "yes")
    return ("None", True) if secure else ("Lax", False)


def get_session_token():
    """Read and sanitize the session_id cookie, or None."""
    raw = request.cookies.get(SESSION_COOKIE_NAME)
    if not raw or not isinstance(raw, str):
        return None
    return raw.strip() or None


def require_auth(f):
    """Route decorator: requires a valid session cookie.

    On success stores the user id in `g.user_id`; otherwise returns 401.
    """

    @wraps(f)
    def wrapper(*args, **kwargs):
        from . import services  # lazy import to avoid a circular import with services

        token = get_session_token()
        user = services.get_user_by_session(token) if token else None
        if not user:
            return jsonify({"error": "נדרשת התחברות"}), 401
        g.user_id = user["id"]
        return f(*args, **kwargs)

    return wrapper
