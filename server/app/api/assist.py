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
from .cases import BODY_MAX_LENGTH

bp = Blueprint("assist", __name__)

# The house style for writing help. This is a character sheet like every
# personality in seed_data, and for the same reason: one line of description
# ("florid and theatrical") produced one register, so every suggestion the
# composer offered came out sounding like the last one.
HOUSE_VOICE = (
    "אתה עוזר הניסוח הרשמי של בית המשפט לתביעות מצחיקות. תפקידך לקחת תלונה "
    "קטנה ולהלביש אותה בשפה משפטית רצינית להפליא.\n\n"
    "**איך אתה כותב:** עברית משפטית גבוהה, מדויקת וחגיגית, בשירות עניין "
    "פעוט לחלוטין. הפער בין הצורה לתוכן הוא כל הבדיחה.\n"
    "**סימני היכר:** מנסח סעיפים כאילו הם מצוטטים מחוק קיים. מתאר רגעים "
    "יומיומיים בלשון של פרוטוקול. נוקב בפרטים מדויקים להחריד.\n"
    "**מה מפעיל אותך:** תלונה מנוסחת ברישול, שאפשר להפוך לכתב תביעה מהודר.\n"
    "**מה שלא תעשה לעולם:** תקרוץ לקורא או תרמוז שזה מצחיק. אתה רציני לגמרי.\n\n"
    "**ככה אתה נשמע:**\n"
    '- "מוגשת בזאת תביעה בעניינה של מדבקת מחיר אשר סירבה לרדת בשלמותה."\n'
    '- "התובע יטען כי המעשה בוצע ביודעין, בשעה 7:04, ובלא כל התראה מוקדמת."\n'
    '- "מתבקש בית המשפט הנכבד להורות על השבת המצב לקדמותו, ולמצער על התנצלות בכתב."'
)


# And the house proofreader, who is emphatically not the house drafter.
#
# HOUSE_VOICE above is a *rewriter*: hand it a shabby complaint and it hands
# back a filing in ceremonial legal Hebrew, which is precisely what
# /assist/draft-lawsuit is for. Pointed at text the user has already written it
# does the same thing and calls the result a correction - the user gets back
# prose they did not write, in a register they did not choose, with their own
# jokes ironed out. The two endpoints would have collapsed into one.
#
# So correction gets its own character sheet, and the whole of that character
# is restraint. The task brief in brain/llm.py carries the hard rules; this
# block is what the model is being, and it is being a person who does not write.
PROOFREADER_VOICE = (
    "אתה המגיה של בית המשפט. אתה מתקן עברית, אתה לא כותב עברית.\n\n"
    "**מה אתה עושה:** כתיב, דקדוק, התאמות, מילות יחס, פיסוק. בשקט, בדיוק, "
    "בלי חוות דעת ובלי הערות שוליים.\n"
    "**מה מפעיל אותך:** שגיאה. רק שגיאה.\n"
    "**מה שלא תעשה לעולם:** תשכתב משפט תקין, תייפה ניסוח, תוסיף הומור, תוסיף "
    "לשון משפטית, או תיגע במילה שאין בה שגיאה. הטקסט שייך למי שכתב אותו, "
    "והעבודה שלך היא שהוא ייראה בדיוק כפי שהתכוון."
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


@bp.post("/assist/correct-text")
@security.require_auth
def correct_text():
    """Hand back what the user wrote, spelled and punctuated properly.

    The third of the spec's writing-help endpoints, and the one that is not
    writing: /assist/draft-lawsuit invents a filing and /assist/suggest-comment
    invents a comment, while this one is given text that already exists and
    must give the same text back. Everything about it - a proofreader instead
    of the house voice, no seeded angle, no `tidy` on the way out - exists to
    stop it drifting into being a third drafter.

    Nothing is published here. The corrected text goes back into the composer
    the user was already filling in, and reaches the database through the
    ordinary publish path, moderation scan included, exactly like text they
    typed themselves.
    """
    data = body_of(request)
    # BODY_MAX_LENGTH is the longest thing any composer on the site can hold (a
    # filing; a comment is shorter). Capping at anything less would silently
    # drop the end of a long filing and return the truncation as a correction.
    text = clean(data.get("text"), BODY_MAX_LENGTH)

    if not text:
        return fail("invalid", "אין טקסט לתיקון.")

    corrected = brain.generate(
        PROOFREADER_VOICE,
        "correct_text",
        {"user_text": text},
        # Derived from the input rather than pinned, because a correction is as
        # long as the thing it corrects. A fixed budget - the 700 the drafter
        # uses - would cap the model mid-filing, and the truncation would look
        # like the proofreader having deleted the user's last two paragraphs.
        # `_max_tokens_for` doubles this again for Hebrew and for thinking.
        max_chars=len(text) + 200,
    )

    return jsonify(
        {
            # The same ceiling the input was held to: a model that loops must
            # not hand the composer more text than the composer can submit.
            "body": clean(corrected, BODY_MAX_LENGTH),
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
