"""REST API routes (Blueprint mounted at /api).

Follows the lecture's REST guidance: plural nouns, sub-resources, proper HTTP
status codes for errors, and limit/offset paging.
"""
from flask import Blueprint, request, jsonify, g, make_response

from . import services
from .utils import (
    require_auth,
    get_session_token,
    session_cookie_flags,
    SESSION_COOKIE_NAME,
)

api = Blueprint("api", __name__, url_prefix="/api")

SESSION_MAX_AGE = 60 * 60 * 24 * 7  # one week


def _auth_response(user: dict, status: int = 200):
    """Build a JSON response that also sets the httpOnly session cookie (lecture 5 flow)."""
    token = services.create_session(user["id"])
    resp = make_response(jsonify({"user": user}), status)
    samesite, secure = session_cookie_flags()
    resp.set_cookie(
        SESSION_COOKIE_NAME, token,
        httponly=True, samesite=samesite, secure=secure,
        max_age=SESSION_MAX_AGE, path="/",
    )
    return resp


# ------------------------------------------------------------------------- auth

@api.post("/auth/signup")
def signup():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip()
    password = data.get("password") or ""
    if not name or not email or not password:
        return jsonify({"error": "נא למלא שם, אימייל וסיסמה"}), 400
    try:
        user = services.create_user(name, email, password)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 409
    return _auth_response(user, 201)


@api.post("/auth/login")
def login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip()
    password = data.get("password") or ""
    if not email or not password:
        return jsonify({"error": "נא להזין אימייל וסיסמה"}), 400
    user = services.authenticate(email, password)
    if not user:
        return jsonify({"error": "אימייל או סיסמה שגויים"}), 401
    return _auth_response(user)


@api.post("/auth/logout")
def logout():
    # Destroy the server-side session and clear the cookie.
    token = get_session_token()
    services.delete_session(token)
    resp = make_response(jsonify({"ok": True}))
    samesite, secure = session_cookie_flags()
    resp.delete_cookie(SESSION_COOKIE_NAME, path="/", samesite=samesite, secure=secure)
    return resp


@api.get("/auth/me")
def me():
    # Resolve the current session cookie to a user (used by the client on load).
    user = services.get_user_by_session(get_session_token())
    if not user:
        return jsonify({"error": "לא מחובר"}), 401
    return jsonify({"user": user})


# ------------------------------------------------------------------------ posts

@api.get("/posts")
def get_posts():
    limit = request.args.get("limit", type=int)
    offset = request.args.get("offset", type=int) or 0
    return jsonify(services.list_posts(limit, offset))


@api.post("/posts")
@require_auth
def create_post():
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    body = (data.get("body") or "").strip()
    defendant = (data.get("defendant") or "").strip()
    location = data.get("location")
    charges = data.get("charges") or []
    if not title or not body or not defendant:
        return jsonify({"error": "נא למלא כותרת, נתבע ותוכן התביעה"}), 400
    post = services.create_post(g.user_id, title, body, defendant, location, charges)
    return jsonify(post), 201


# ------------------------------------------------------------------------ users

@api.get("/users")
def get_users():
    search = request.args.get("search")
    limit = request.args.get("limit", type=int)
    offset = request.args.get("offset", type=int) or 0
    return jsonify(services.list_users(search, limit, offset))


@api.get("/users/<int:user_id>")
def get_user(user_id):
    profile = services.get_user_profile(user_id)
    if not profile:
        return jsonify({"error": "התובע לא נמצא"}), 404
    return jsonify(profile)
