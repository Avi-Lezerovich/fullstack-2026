"""Filing, browsing and withdrawing lawsuits."""

from __future__ import annotations

from flask import Blueprint, g, jsonify, request

from .. import security
from ..errors import fail
from ..services import cases_service, users_service
from ..validation import body_of, clean, positive_int

bp = Blueprint("cases", __name__)

MAX_PAGE_SIZE = 50
BODY_MAX_LENGTH = 8000


@bp.get("/cases")
@security.optional_auth
def list_cases():
    """The feed. Works signed out; a signed-in viewer additionally learns which
    cases they have already liked."""
    limit = positive_int(request.args.get("limit"), 20, maximum=MAX_PAGE_SIZE)
    offset = positive_int(request.args.get("offset"), 0)
    author_id = request.args.get("author_id", type=int)
    status = clean(request.args.get("status"), 32) or None

    cases = cases_service.list_cases(
        viewer_id=g.user_id, author_id=author_id, status=status, limit=limit, offset=offset
    )
    total = cases_service.count_cases(author_id=author_id, status=status)
    return jsonify({"cases": cases, "total": total, "limit": limit, "offset": offset}), 200


@bp.post("/cases")
@security.require_auth
def create_case():
    data = body_of(request)
    title = clean(data.get("title"), cases_service.TITLE_MAX_LENGTH)
    body = clean(data.get("body"), BODY_MAX_LENGTH)
    defendant_text = clean(data.get("defendant_text"), 255)
    image_url = clean(data.get("image_url"), 1024) or None
    defendant_user_id = data.get("defendant_user_id")

    if len(title) < 3:
        return fail("invalid", "כותרת התביעה קצרה מדי.")
    if len(body) < 10:
        return fail("invalid", "כתב התביעה קצר מדי.")

    if defendant_user_id is not None:
        try:
            defendant_user_id = int(defendant_user_id)
        except (TypeError, ValueError):
            return fail("invalid", "הנתבע שנבחר אינו תקין.")

        if defendant_user_id == g.user_id:
            return fail("invalid", "אי אפשר לתבוע את עצמך.")

        defendant = users_service.get_by_id(defendant_user_id)
        if defendant is None or defendant["status"] != "active":
            return fail("invalid", "הנתבע שנבחר אינו קיים.")
        # Keep the free-text field meaningful even when a real user is named,
        # so the card reads the same either way.
        defendant_text = defendant_text or defendant["name"]

    if not defendant_text:
        return fail("invalid", "יש לציין נגד מי מוגשת התביעה.")

    result, case_id = cases_service.create_case(
        g.user_id,
        title,
        body,
        defendant_text,
        defendant_user_id=defendant_user_id,
        charges=data.get("charges"),
        image_url=image_url,
    )
    if result == "rejected":
        # 422, not 400: the request was well-formed, we simply refuse to
        # publish it. The row exists for the admin queue but is never public.
        return fail("rejected", "כתב התביעה נחסם על ידי מנגנון סינון התוכן.")
    if result != "ok":
        return fail(result)

    case = cases_service.get_case(case_id, viewer_id=g.user_id)
    return jsonify({"case": case}), 201


@bp.get("/cases/<int:case_id>")
@security.optional_auth
def get_case(case_id: int):
    case = cases_service.get_case(
        case_id,
        viewer_id=g.user_id,
        viewer_is_admin=bool(g.user and g.user.get("is_admin")),
    )
    if case is None:
        return fail("not_found", "התיק המבוקש לא נמצא.")
    return jsonify({"case": case}), 200


@bp.delete("/cases/<int:case_id>")
@security.require_auth
def delete_case(case_id: int):
    result = cases_service.delete_case(case_id, g.user_id)
    if result == "not_found":
        return fail("not_found", "התיק המבוקש לא נמצא.")
    if result == "forbidden":
        return fail("forbidden", "רק מגיש התביעה יכול למשוך אותה.")
    if result == "closed":
        return fail("closed", "לא ניתן למשוך תביעה אחרי שהורכב הרכב מושבעים.")
    return jsonify({"ok": True}), 200
