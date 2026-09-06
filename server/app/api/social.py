"""Likes, follows and comments - the ordinary social surface of a case."""

from __future__ import annotations

from flask import Blueprint, g, jsonify, request

from .. import security
from ..errors import fail
from ..services import cases_service, comments_service, follows_service, likes_service
from ..validation import body_of, clean

bp = Blueprint("social", __name__)


@bp.post("/cases/<int:case_id>/like")
@security.require_auth
def toggle_like(case_id: int):
    """One endpoint for both directions: the server owns the current state, so
    the client cannot get out of step by guessing it."""
    result, payload = likes_service.toggle_like(case_id, g.user_id)
    if result != "ok":
        return fail("not_found", "התיק המבוקש לא נמצא.")
    return jsonify(payload), 200


@bp.post("/cases/<int:case_id>/follow")
@security.require_auth
def toggle_follow(case_id: int):
    """Both directions again, for the same reason the like endpoint is one."""
    result, payload = follows_service.toggle_follow(case_id, g.user_id)
    if result != "ok":
        return fail("not_found", "התיק המבוקש לא נמצא.")
    return jsonify(payload), 200


@bp.get("/cases/<int:case_id>/likes")
@security.optional_auth
def list_likers(case_id: int):
    """Who liked a case. Behind the same visibility rule as the case itself -
    a hidden filing must not leak its audience either."""
    case = cases_service.get_case(
        case_id,
        viewer_id=g.user_id,
        viewer_is_admin=bool(g.user and g.user.get("is_admin")),
    )
    if case is None:
        return fail("not_found", "התיק המבוקש לא נמצא.")
    return jsonify({"users": likes_service.likers(case_id)}), 200


@bp.get("/cases/<int:case_id>/followers")
@security.optional_auth
def list_followers(case_id: int):
    """Who tracks a case. Behind the same visibility rule as the likers list -
    a hidden filing must not leak its audience either."""
    case = cases_service.get_case(
        case_id,
        viewer_id=g.user_id,
        viewer_is_admin=bool(g.user and g.user.get("is_admin")),
    )
    if case is None:
        return fail("not_found", "התיק המבוקש לא נמצא.")
    return jsonify({"users": follows_service.followers(case_id)}), 200


@bp.get("/cases/<int:case_id>/comments")
@security.optional_auth
def list_comments(case_id: int):
    """The thread, behind the same visibility rule as the case itself.

    The guard is not redundant with `shape_comment`'s redaction, because the
    two answer different questions. Hiding a case does not cascade to its
    comments - the case row becomes 'hidden' and every comment on it stays
    'published' - and `shape_comment` decides redaction from the *comment's*
    own status, which is right for a hidden reply on a public case and says
    nothing at all about a public reply on a hidden one.

    Without this, a filing hidden for harassment kept the entire argument on it
    readable to anybody holding the case id, while `/likes` and `/followers`,
    which leak considerably less, were both closed.
    """
    case = cases_service.get_case(
        case_id,
        viewer_id=g.user_id,
        viewer_is_admin=bool(g.user and g.user.get("is_admin")),
    )
    if case is None:
        return fail("not_found", "התיק המבוקש לא נמצא.")

    comments = comments_service.list_for_case(
        case_id,
        viewer_id=g.user_id,
        viewer_is_admin=bool(g.user and g.user.get("is_admin")),
    )
    return jsonify({"comments": comments}), 200


@bp.post("/cases/<int:case_id>/comments")
@security.require_auth
def create_comment(case_id: int):
    data = body_of(request)
    body = clean(data.get("body"), comments_service.BODY_MAX_LENGTH)
    parent_comment_id = data.get("parent_comment_id")

    if not body:
        return fail("invalid", "לא ניתן לשלוח תגובה ריקה.")

    if parent_comment_id is not None:
        try:
            parent_comment_id = int(parent_comment_id)
        except (TypeError, ValueError):
            return fail("invalid", "התגובה שאליה ניסית להשיב אינה תקינה.")

    # This endpoint only ever creates role='user'. Testimony has its own
    # endpoint with its own permission rules, and the trial roles are written
    # by the worker alone.
    result, comment_id = comments_service.create_comment(
        case_id, g.user_id, body, role="user", parent_comment_id=parent_comment_id
    )

    if result == "not_found":
        return fail("not_found", "התיק המבוקש לא נמצא.")
    if result == "invalid":
        return fail("invalid", "התגובה אינה תקינה.")
    if result == "rejected":
        return fail("rejected", "התגובה נחסמה על ידי מנגנון סינון התוכן.")

    return jsonify(
        {"comment": comments_service.get_shaped(comment_id, viewer_id=g.user_id)}
    ), 201
