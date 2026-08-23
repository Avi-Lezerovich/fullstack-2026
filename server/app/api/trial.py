"""Trial actions and the trial read model.

Separate from cases.py because these endpoints have a completely different
permission model: gated by phase, and by whether you are a party to the case.
"""

from __future__ import annotations

from flask import Blueprint, g, jsonify, request

from .. import security
from ..errors import fail
from ..services import (
    agents_service,
    cases_service,
    comments_service,
    jury_service,
    summons_service,
)
from ..validation import body_of, clean

bp = Blueprint("trial", __name__)


def _shape_member(row) -> dict:
    return {
        "seat": int(row["seat"]),
        "juror": {
            "id": row["juror_user_id"],
            "name": row["juror_name"],
            "avatar_url": row["avatar_url"],
            "is_bot": True,
            "personality_name": row.get("personality_name"),
        },
        # Absolute, so the UI can show when a juror is expected to speak.
        "speaks_at": row["speaks_at"].isoformat(timespec="seconds") if row["speaks_at"] else None,
        "spoke_at": row["spoke_at"].isoformat(timespec="seconds") if row["spoke_at"] else None,
        # Null until they speak - the panel shows who is still to be heard.
        "vote": row["vote"],
        "comment_id": row["comment_id"],
    }


@bp.get("/cases/<int:case_id>/trial")
@security.optional_auth
def get_trial(case_id: int):
    """Everything about the trial itself: the panel, the votes, the witnesses.

    Also reports what the VIEWER may do right now, so the client never has to
    reimplement the phase and party rules to decide which buttons to show.
    """
    case = cases_service.get_raw(case_id)
    if case is None:
        return fail("not_found", "התיק המבוקש לא נמצא.")

    panel = jury_service.get_panel(case_id)
    members = jury_service.get_members(case_id)
    summonses = summons_service.list_for_case(case_id)

    viewer_side = summons_service.side_for(case, g.user_id) if g.user_id else None
    counts = summons_service.counts_by_side(case_id)
    my_summons = next(
        (s for s in summonses if g.user_id and s["witness"]["id"] == g.user_id), None
    )

    return jsonify(
        {
            "panel": (
                {
                    "judge": {
                        "id": panel["judge_user_id"],
                        "name": panel["judge_name"],
                        "personality_name": panel["judge_personality"],
                        "is_bot": True,
                    },
                    "tally_guilty": panel["tally_guilty"],
                    "tally_not_guilty": panel["tally_not_guilty"],
                    "tiebreak_used": bool(panel["tiebreak_used"]),
                    "members": [_shape_member(row) for row in members],
                }
                if panel
                else None
            ),
            "summons": summonses,
            "viewer": {
                "side": viewer_side,
                # A party may summon while the phase is open and their side has
                # room; the client just reads this.
                "can_summon": bool(
                    viewer_side
                    and case["status"] == "witness_phase"
                    and counts[viewer_side] < summons_service.MAX_WITNESSES_PER_SIDE
                ),
                "summons_remaining": (
                    summons_service.MAX_WITNESSES_PER_SIDE - counts[viewer_side]
                    if viewer_side
                    else 0
                ),
                "can_testify": bool(
                    my_summons
                    and my_summons["status"] == "pending"
                    and case["status"] == "witness_phase"
                ),
            },
        }
    ), 200


@bp.post("/cases/<int:case_id>/summons")
@security.require_auth
def summon_witness(case_id: int):
    data = body_of(request)
    try:
        witness_id = int(data.get("witness_user_id"))
    except (TypeError, ValueError):
        return fail("invalid", "יש לבחור עד.")

    result, _summons_id = summons_service.summon(case_id, g.user_id, witness_id)

    messages = {
        "not_found": "התיק או המשתמש המבוקש לא נמצאו.",
        "closed": "שלב איסוף העדויות הסתיים.",
        "forbidden": "רק צד לתיק רשאי לזמן עדים.",
        "invalid": "אפשר לזמן רק משתמשים אנושיים שאינם צד לתיק.",
        "conflict": "העד כבר זומן, או שניצלת את מכסת שלושת העדים.",
    }
    if result != "ok":
        return fail(result, messages.get(result))

    return jsonify({"summons": summons_service.list_for_case(case_id)}), 201


@bp.post("/cases/<int:case_id>/testify")
@security.require_auth
def testify(case_id: int):
    data = body_of(request)
    body = clean(data.get("body"), comments_service.BODY_MAX_LENGTH)
    if not body:
        return fail("invalid", "לא ניתן למסור עדות ריקה.")

    result, comment_id = summons_service.testify(case_id, g.user_id, body)

    messages = {
        "not_found": "התיק המבוקש לא נמצא.",
        "closed": "שלב איסוף העדויות הסתיים.",
        "forbidden": "רק עד שזומן לתיק רשאי למסור עדות.",
        "conflict": "כבר מסרת עדות בתיק הזה.",
        "invalid": "העדות אינה תקינה.",
    }
    if result != "ok":
        return fail(result, messages.get(result))

    return jsonify({"comment_id": comment_id}), 201


@bp.get("/me/summons")
@security.require_auth
def my_summons():
    """Cases waiting on me to testify."""
    return jsonify({"summons": summons_service.pending_for_user(g.user_id)}), 200


@bp.get("/agents")
def list_agents():
    """The court's permanent staff, for an "about the bots" view."""
    roster = []
    for role in ("juror", "judge", "moderator"):
        for user_id in agents_service.pool_ids(role):
            agent = agents_service.get_agent(user_id)
            roster.append(
                {
                    "id": agent["user_id"],
                    "name": agent["name"],
                    "role": agent["role"],
                    "moderator_kind": agent["moderator_kind"],
                    "personality_name": agent["personality_name"],
                    "tone_tag": agent["tone_tag"],
                }
            )
    return jsonify({"agents": roster}), 200
