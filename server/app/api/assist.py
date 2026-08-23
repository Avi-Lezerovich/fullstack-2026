"""AI writing help.

The same `generate()` the jurors use, pointed at the user's own composer. With
no API key configured this is the deterministic offline generator, so the
feature works in a fresh checkout with nothing set up - which is the whole
reason the offline path is the default rather than a fallback.

Nothing here writes to the database. A suggestion is a suggestion: the user
still has to submit it, and it is screened at publish time like any other text.
"""

from __future__ import annotations

from flask import Blueprint, g, jsonify, request

from .. import brain, security
from ..errors import fail
from ..services import agents_service, cases_service
from ..validation import body_of, clean

bp = Blueprint("assist", __name__)

# The house style for writing help: florid and theatrical, because a lawsuit
# against Monday should not read like a memo.
HOUSE_VOICE = (
    "אתה עוזר ניסוח בבית המשפט לתביעות מצחיקות. אתה כותב בעברית, בנימה "
    "משפטית-סאטירית, קצר ולעניין. [tone:theatrical]"
)


@bp.post("/assist/draft-lawsuit")
@security.require_auth
def draft_lawsuit():
    """Draft a filing from whatever the user has typed so far."""
    data = body_of(request)
    defendant = clean(data.get("defendant_text"), 255)
    title = clean(data.get("title"), 512)
    hint = clean(data.get("hint"), 500)

    if not defendant and not title and not hint:
        return fail("invalid", "יש לציין לפחות נגד מי התביעה.")

    context = {
        "defendant": defendant or "הנתבע",
        "case_title": title or f"התביעה נגד {defendant}",
        "charges": cases_service.clean_charges(data.get("charges")),
        "case_body": hint,
    }
    return jsonify(
        {
            "body": brain.generate(HOUSE_VOICE, "draft_lawsuit", context, max_chars=700),
            "backend": "llm" if _live() else "offline",
        }
    ), 200


@bp.post("/assist/suggest-comment")
@security.require_auth
def suggest_comment():
    """Suggest a comment for a case the user is looking at."""
    data = body_of(request)
    try:
        case_id = int(data.get("case_id"))
    except (TypeError, ValueError):
        return fail("invalid", "התיק אינו תקין.")

    case = cases_service.get_case(case_id, viewer_id=g.user_id)
    if case is None:
        return fail("not_found", "התיק המבוקש לא נמצא.")

    context = {
        "case_title": case["title"],
        "case_body": (case["body"] or "")[:600],
        "defendant": case["defendant_text"],
        "charges": case["charges"],
    }
    return jsonify(
        {
            "body": brain.generate(HOUSE_VOICE, "suggest_comment", context, max_chars=280),
            "backend": "llm" if _live() else "offline",
        }
    ), 200


@bp.post("/assist/in-character")
@security.require_auth
def in_character():
    """Rewrite in the voice of one of the court's personalities - the same
    seam the bots use, exposed for fun."""
    data = body_of(request)
    hint = clean(data.get("hint"), 500)
    try:
        agent_id = int(data.get("agent_user_id"))
    except (TypeError, ValueError):
        return fail("invalid", "יש לבחור דמות.")

    agent = agents_service.get_agent(agent_id)
    if agent is None:
        return fail("not_found", "הדמות לא נמצאה.")

    return jsonify(
        {
            "body": brain.generate(
                agent["personality_prompt"], "suggest_comment", {"case_body": hint}, max_chars=280
            ),
            "personality_name": agent["personality_name"],
        }
    ), 200


def _live() -> bool:
    from ..config import get_settings

    return get_settings().use_llm
