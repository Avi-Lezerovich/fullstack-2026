"""REST API routes (Blueprint mounted at /api).

Follows the lecture's REST guidance: plural nouns, sub-resources, proper HTTP
status codes for errors, and limit/offset paging.
"""
import os
import secrets

from flask import Blueprint, request, jsonify, g, make_response, send_from_directory
from werkzeug.utils import secure_filename

from . import services
from .models import UPLOAD_DIR
from .utils import (
    require_auth,
    get_session_token,
    session_cookie_flags,
    SESSION_COOKIE_NAME,
)

api = Blueprint("api", __name__, url_prefix="/api")

SESSION_MAX_AGE = 60 * 60 * 24 * 7  # one week

# Image upload constraints.
MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MB
ALLOWED_IMAGE_EXTS = {"jpg", "jpeg", "png", "webp", "gif"}
ALLOWED_IMAGE_MIMES = {"image/jpeg", "image/png", "image/webp", "image/gif"}


def _current_user_id():
    """Resolve the session cookie to a user id, or None (for optionally-auth routes)."""
    user = services.get_user_by_session(get_session_token())
    return user["id"] if user else None


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
    follower_id = None
    if request.args.get("feed") == "following":
        follower_id = _current_user_id()
        if not follower_id:
            return jsonify({"error": "נדרשת התחברות"}), 401
    return jsonify(services.list_posts(limit, offset, follower_id=follower_id))


@api.post("/posts")
@require_auth
def create_post():
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    body = (data.get("body") or "").strip()
    defendant = (data.get("defendant") or "").strip()
    charges = data.get("charges") or []
    image_url = (data.get("image_url") or "").strip() or None
    if not title or not body or not defendant:
        return jsonify({"error": "נא למלא כותרת, נתבע ותוכן התביעה"}), 400
    post = services.create_post(g.user_id, title, body, defendant, charges, image_url)
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
    profile = services.get_user_profile(user_id, viewer_id=_current_user_id())
    if not profile:
        return jsonify({"error": "התובע לא נמצא"}), 404
    return jsonify(profile)


@api.patch("/users/me")
@require_auth
def update_me():
    data = request.get_json(silent=True) or {}
    bio = data.get("bio")
    avatar_url = data.get("avatar_url")
    if bio is not None:
        bio = str(bio).strip()
    user = services.update_profile(g.user_id, bio=bio, avatar_url=avatar_url)
    return jsonify({"user": user})


# ----------------------------------------------------------------------- follows

@api.post("/users/<int:user_id>/follow")
@require_auth
def follow(user_id):
    if user_id == g.user_id:
        return jsonify({"error": "אי אפשר לעקוב אחרי עצמך"}), 400
    if not services.user_exists(user_id):
        return jsonify({"error": "התובע לא נמצא"}), 404
    services.follow_user(g.user_id, user_id)
    return jsonify({"ok": True, "is_following": True})


@api.delete("/users/<int:user_id>/follow")
@require_auth
def unfollow(user_id):
    services.unfollow_user(g.user_id, user_id)
    return jsonify({"ok": True, "is_following": False})


# ----------------------------------------------------------------------- uploads

@api.post("/uploads")
@require_auth
def upload_image():
    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify({"error": "לא נבחר קובץ"}), 400

    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED_IMAGE_EXTS or file.mimetype not in ALLOWED_IMAGE_MIMES:
        return jsonify({"error": "סוג קובץ לא נתמך (jpg, png, webp, gif בלבד)"}), 400

    # Size check without trusting the client: seek to end, read the offset, rewind.
    file.seek(0, os.SEEK_END)
    size = file.tell()
    file.seek(0)
    if size > MAX_UPLOAD_BYTES:
        return jsonify({"error": "הקובץ גדול מדי (עד 5MB)"}), 400

    os.makedirs(UPLOAD_DIR, exist_ok=True)
    name = f"{secrets.token_hex(16)}.{ext}"
    # secure_filename guards the generated name; it's already random so this is belt-and-braces.
    file.save(os.path.join(UPLOAD_DIR, secure_filename(name)))
    return jsonify({"url": f"/api/uploads/{name}"}), 201


@api.get("/uploads/<path:filename>")
def serve_upload(filename):
    return send_from_directory(UPLOAD_DIR, filename)
