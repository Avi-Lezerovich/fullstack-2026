"""The ops half of the admin dashboard: AI usage and the site overview tiles.

Split from moderation.py because these endpoints answer a different question -
not "what needs a human's judgment" but "is the machinery healthy" - even
though both sit behind the same `require_admin` gate and the same dashboard.
System health itself is not here: `GET /api/health` already answers it and is
already unauthenticated, so the admin UI calls that endpoint directly rather
than through a second, admin-gated copy of the same data.
"""

from __future__ import annotations

from flask import Blueprint, jsonify

from .. import security
from ..services import brain_usage_service, cases_service, moderation_service, users_service

bp = Blueprint("admin_ops", __name__)

# Every case status except 'closed' - a case is "active" for as long as the
# trial engine still has something left to do with it.
_OPEN_CASE_STATUSES = tuple(s for s in cases_service.CASE_STATUSES if s != "closed")


@bp.get("/admin/brain/usage")
@security.require_admin
def admin_brain_usage():
    return jsonify(
        {
            "today": brain_usage_service.usage_today(),
            "week": brain_usage_service.usage_this_week(),
            # Per KEY, not per vendor. Quota belongs to a credential and a
            # model, so "Gemini is at 900" says nothing useful once there is
            # more than one key - it is the one that is exhausted that matters.
            "credentials": brain_usage_service.credential_quotas(),
            "by_credential": brain_usage_service.usage_by_credential(),
            "by_credential_week": brain_usage_service.usage_by_credential(days=7),
            # Why calls are failing, not just how many. Without this the tab
            # cannot tell "near the quota" apart from "every call is erroring",
            # which are the same picture and completely different problems.
            "failures": brain_usage_service.recent_failures(),
        }
    ), 200


@bp.get("/admin/overview")
@security.require_admin
def admin_overview():
    return jsonify(
        {
            "total_users": users_service.count_users(include_bots=False, status="active"),
            "open_cases": cases_service.count_cases(status=_OPEN_CASE_STATUSES),
            "pending_reports": moderation_service.count_reports(status="pending"),
            "banned_users": users_service.count_users(status="banned"),
        }
    ), 200
