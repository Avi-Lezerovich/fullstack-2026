"""Browsing people - including the nineteen bots, who are people here too."""

from __future__ import annotations

from flask import Blueprint, g, jsonify, request

from .. import security
from ..errors import fail
from ..services import cases_service, users_service
from ..validation import body_of, clean, name_problem, positive_int

bp = Blueprint("users", __name__)

BIO_MAX_LENGTH = 500


@bp.get("/users")
@security.optional_auth
def list_users():
    query = clean(request.args.get("search"), 100)
    limit = positive_int(request.args.get("limit"), 20, maximum=50)
    offset = positive_int(request.args.get("offset"), 0)
    # Used by the summons dialog, where bots are not eligible witnesses.
    include_bots = request.args.get("include_bots", "1") != "0"

    users = users_service.search_users(
        query, limit=limit, offset=offset, include_bots=include_bots
    )
    # `total` is what lets the directory page past the first fifty. It counts
    # the same filters the list applies, so the two cannot disagree.
    total = users_service.count_users(query, include_bots=include_bots)
    return jsonify(
        {"users": users, "total": total, "limit": limit, "offset": offset}
    ), 200


@bp.get("/users/<int:user_id>")
@security.optional_auth
def get_user(user_id: int):
    row = users_service.get_by_id(user_id)
    if row is None or row["status"] == "banned":
        return fail("not_found", "המשתמש/ת  המבוקש לא נמצא.")

    profile = users_service.public_user(row)
    profile["case_count"] = cases_service.count_cases(author_id=user_id)
    return jsonify({"user": profile}), 200


@bp.patch("/users/me")
@security.require_auth
def update_me():
    data = body_of(request)
    name = clean(data.get("name"), 200) if "name" in data else None
    bio = clean(data.get("bio"), BIO_MAX_LENGTH) if "bio" in data else None
    avatar_url = clean(data.get("avatar_url"), 1024) if "avatar_url" in data else None

    if name is not None and (problem := name_problem(name)):
        return fail("invalid", problem)

    users_service.update_profile(g.user_id, name=name, bio=bio, avatar_url=avatar_url)
    return jsonify({"user": users_service.private_user(users_service.get_by_id(g.user_id))}), 200
