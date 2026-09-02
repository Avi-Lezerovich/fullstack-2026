"""Signing up, signing in, signing out, and who am I."""

from __future__ import annotations

from flask import Blueprint, g, jsonify, request

from .. import mail, security
from ..config import get_settings
from ..errors import fail
from ..services import auth_service, users_service
from ..validation import body_of, clean, is_email, name_problem

bp = Blueprint("auth", __name__)


def _authenticated_response(user: dict, status: int = 200):
    """Mint a session and attach the cookie. The one place that happens."""
    settings = get_settings()
    raw_token = auth_service.create_session(user["id"], ttl_days=settings.session_ttl_days)
    response = jsonify({"user": users_service.private_user(user)})
    security.set_session_cookie(response, raw_token, settings)
    return response, status


@bp.post("/auth/signup")
def signup():
    data = body_of(request)
    name = clean(data.get("name"), 200)
    email = clean(data.get("email"), 320).lower()
    password = data.get("password") or ""

    if problem := name_problem(name):
        return fail("invalid", problem)
    if not is_email(email):
        return fail("invalid", "כתובת האימייל אינה תקינה.")
    # Checked before hashing: bcrypt 5 raises on anything over 72 bytes rather
    # than truncating it.
    if problem := security.password_problem(password):
        return fail("invalid", problem)

    result, user_id = users_service.create_user(
        name, email, security.hash_password(password)
    )
    if result == "conflict":
        return fail("conflict", "כתובת האימייל הזו כבר רשומה במערכת.")

    user = users_service.get_by_id(user_id)
    return _authenticated_response(user, status=201)


@bp.post("/auth/login")
def login():
    data = body_of(request)
    email = clean(data.get("email"), 320).lower()
    password = data.get("password") or ""

    user = users_service.get_by_email(email) if email else None

    # One message and one code for "no such account" and "wrong password", so
    # the endpoint cannot be used to discover which addresses are registered.
    if user is None or not security.verify_password(password, user["password_hash"]):
        return fail("unauthorized", "כתובת האימייל או הסיסמה שגויות.")

    if user["status"] == "banned":
        return fail("forbidden", "החשבון הזה הושעה על ידי בית המשפט.")

    return _authenticated_response(user)


@bp.post("/auth/logout")
def logout():
    """Always succeeds - signing out an already-invalid session is not an
    error, and reporting one would only strand the browser's cookie."""
    auth_service.delete_session(request.cookies.get(security.COOKIE_NAME))
    response = jsonify({"ok": True})
    security.clear_session_cookie(response)
    return response, 200


# --- password reset ---------------------------------------------------------
#
# Two endpoints. The first always answers the same way, so it cannot be used to
# discover which addresses are registered. The second spends the token exactly
# once and signs the account out everywhere.


@bp.post("/auth/password-reset/request")
def request_password_reset():
    data = body_of(request)
    email = clean(data.get("email"), 320).lower()

    # Deliberately identical for a known address, an unknown one, a banned
    # account and a malformed string.
    generic = jsonify(
        {"ok": True, "message": "אם הכתובת רשומה במערכת, נשלח אליה קישור לאיפוס הסיסמה."}
    ), 200

    if not is_email(email):
        return generic

    settings = get_settings()
    user = users_service.get_by_email(email)
    if user is None or user["status"] == "banned":
        return generic

    # Already sent one a moment ago. Still the generic answer - a "slow down"
    # here would tell an attacker the address is registered, which is exactly
    # what the rest of this endpoint refuses to say.
    if auth_service.reset_requested_recently(
        user["id"], settings.reset_cooldown_seconds
    ):
        return generic

    raw_token = auth_service.issue_password_reset(
        user["id"], ttl_minutes=settings.reset_ttl_minutes
    )

    reset_url = f"{settings.client_origin.rstrip('/')}/reset-password?token={raw_token}"
    mail.send_mail_async(
        to=user["email"],
        subject="איפוס סיסמה - LolSuit",
        body=mail.password_reset_body(user["name"], reset_url, settings.reset_ttl_minutes),
    )
    return generic


@bp.post("/auth/password-reset/confirm")
def confirm_password_reset():
    data = body_of(request)
    token = clean(data.get("token"), 200)
    password = data.get("password") or ""

    if not token:
        return fail("invalid", "חסר טוקן איפוס.")
    if problem := security.password_problem(password):
        return fail("invalid", problem)

    result, _user_id = auth_service.reset_password(token, security.hash_password(password))
    if result != "ok":
        return fail("invalid", "קישור האיפוס אינו תקף או שכבר נעשה בו שימוש.")

    return jsonify({"ok": True, "message": "הסיסמה עודכנה. אפשר להתחבר מחדש."}), 200


@bp.get("/auth/me")
@security.optional_auth
def me():
    """Anonymous is a normal answer here, not an error: the front end calls
    this on load to decide what to render."""
    if g.user is None:
        return jsonify({"user": None}), 200
    return jsonify({"user": users_service.private_user(g.user)}), 200
