"""Reporting content, and the human admin dashboard.

Both live here so the override sits next to what it overrides: the same
endpoint shape a bot uses to hide something is what an admin uses to put it
back, and both write to the same audit trail.
"""

from __future__ import annotations

from flask import Blueprint, g, jsonify, request

from .. import security
from ..errors import fail
from ..services import moderation_service, users_service
from ..validation import body_of, clean, positive_int

bp = Blueprint("moderation", __name__)

REPORT_REASONS = ("abuse", "spam", "off_topic", "harassment", "other")


@bp.post("/reports")
@security.require_auth
def create_report():
    data = body_of(request)
    target_type = clean(data.get("target_type"), 16)
    reason = clean(data.get("reason"), 64) or "other"
    details = clean(data.get("details"), 1000) or None

    try:
        target_id = int(data.get("target_id"))
    except (TypeError, ValueError):
        return fail("invalid", "הפריט המדווח אינו תקין.")

    if target_type not in ("case", "comment"):
        return fail("invalid", "סוג הפריט אינו נתמך.")
    if reason not in REPORT_REASONS:
        reason = "other"

    result, report_id = moderation_service.report(
        target_type, target_id, g.user_id, reason, details
    )
    if result == "not_found":
        return fail("not_found", "הפריט המדווח לא נמצא.")
    if result == "conflict":
        return fail("conflict", "כבר דיווחת על הפריט הזה.")
    if result != "ok":
        return fail(result)

    return jsonify(
        {"report_id": report_id, "message": "הדיווח התקבל ויטופל על ידי צוות הפיקוח."}
    ), 201


# --- the admin dashboard ----------------------------------------------------


@bp.get("/admin/queue")
@security.require_admin
def admin_queue():
    status = clean(request.args.get("status"), 32) or None
    limit = positive_int(request.args.get("limit"), 50, maximum=200)
    return jsonify({"reports": moderation_service.list_reports(status, limit)}), 200


@bp.get("/admin/flagged")
@security.require_admin
def admin_flagged():
    """Everything not currently published - flagged, hidden and rejected."""
    limit = positive_int(request.args.get("limit"), 50, maximum=200)
    return jsonify({"items": moderation_service.flagged_content(limit)}), 200


@bp.get("/admin/history/<target_type>/<int:target_id>")
@security.require_admin
def admin_history(target_type: str, target_id: int):
    if target_type not in ("case", "comment", "user", "report"):
        return fail("invalid", "סוג הפריט אינו נתמך.")
    return jsonify({"history": moderation_service.history(target_type, target_id)}), 200


@bp.post("/admin/content/<target_type>/<int:target_id>/status")
@security.require_admin
def admin_set_status(target_type: str, target_id: int):
    """Set ANY status, including putting hidden content back.

    This is the override the course requires: a human can reverse any bot
    decision, and because the action is recorded with its previous status the
    reversal is visible in the trail rather than silently rewriting history.
    """
    data = body_of(request)
    new_status = clean(data.get("status"), 16)
    reason = clean(data.get("reason"), 255) or "החלטת מנהל."

    if target_type not in ("case", "comment"):
        return fail("invalid", "סוג הפריט אינו נתמך.")
    if new_status not in moderation_service.CONTENT_STATUSES:
        return fail("invalid", "סטטוס לא חוקי.")

    result = moderation_service.set_content_status(
        target_type,
        target_id,
        new_status,
        actor_id=g.user_id,
        actor_is_bot=False,
        action="override",
        reason=reason,
    )
    if result == "not_found":
        return fail("not_found", "הפריט לא נמצא.")
    if result == "invalid":
        return fail("invalid")

    return jsonify({"ok": True, "status": new_status, "changed": result == "ok"}), 200


@bp.post("/admin/reports/<int:report_id>/resolve")
@security.require_admin
def admin_resolve_report(report_id: int):
    data = body_of(request)
    decision = clean(data.get("decision"), 32)
    note = clean(data.get("note"), 255) or None

    allowed = (
        moderation_service.RESOLVED_HIDDEN,
        moderation_service.RESOLVED_DISMISSED,
        moderation_service.RESOLVED_BANNED,
    )
    if decision not in allowed:
        return fail("invalid", "החלטה לא חוקית.")

    # admin_resolve, not resolve_report: the decision has to be carried out,
    # not merely recorded. "resolved_hidden" hides the content and
    # "resolved_banned" also suspends its author.
    result = moderation_service.admin_resolve(
        report_id, decision, actor_id=g.user_id, note=note
    )
    if result == "not_found":
        return fail("not_found", "הדיווח או התוכן המדווח לא נמצאו.")
    if result == "invalid":
        return fail("invalid", "אי אפשר להשעות את עצמך.")
    if result != "ok":
        return fail("conflict", "הדיווח כבר טופל.")
    return jsonify({"ok": True}), 200


@bp.post("/admin/users/<int:user_id>/ban")
@security.require_admin
def admin_ban(user_id: int):
    data = body_of(request)
    reason = clean(data.get("reason"), 255) or "החלטת מנהל."

    if users_service.get_by_id(user_id) is None:
        return fail("not_found", "המשתמש לא נמצא.")
    if user_id == g.user_id:
        return fail("invalid", "אי אפשר להשעות את עצמך.")

    result = moderation_service.ban_user(user_id, actor_id=g.user_id, reason=reason)
    return jsonify({"ok": True, "changed": result == "ok"}), 200


@bp.post("/admin/users/<int:user_id>/unban")
@security.require_admin
def admin_unban(user_id: int):
    if users_service.get_by_id(user_id) is None:
        return fail("not_found", "המשתמש לא נמצא.")
    result = moderation_service.unban_user(user_id, actor_id=g.user_id)
    return jsonify({"ok": True, "changed": result == "ok"}), 200
