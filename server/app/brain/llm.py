"""The optional live backend - one provider-neutral seam.

Only used when the configured provider is actually credentialed. The provider
SDK is imported inside its completion function so the package stays genuinely
optional - the application, the test suite and the Docker image all still run
without it, on the offline generator.

Adding a provider is one entry in `PROVIDERS` and nothing else. Everything
above this module - the prompt, the tasks, the callers - is unchanged by that,
which is the whole reason no vendor is named outside this file.

Providers do not agree on what "credentialed" means, so each one says for
itself: Bedrock authenticates through the AWS credential chain and has no API
key at all, while the direct Anthropic API has nothing but one.

This module is allowed to raise. Every failure mode - unknown provider, missing
package, missing credentials, bad key, rate limit, timeout, empty completion,
network down - lands in the same `except` in brain/__init__.py and falls back to
the offline generator. The worker therefore has no LLM-shaped failure mode.

--- on getting interesting text out of it -------------------------------------

The first version of this file asked for "a sentence or two, in Hebrew, in
character" and got back exactly what it asked for: correct, in-character, and
identical in shape every single time. Three things fixed that, and they are all
prompt-side, because **the sampling parameters no longer exist**: temperature,
top_p and top_k were removed from the Messages API on current models and are
rejected outright, so variety cannot be bought with a dial.

1. The system prompt describes a *world* and a *register*, not a word count.
2. The task briefs are directorial - they name moves the character can make -
   instead of prescribing one shape to fill in.
3. Every call draws a seeded ANGLE: one rhetorical move plus a length. It is
   seeded from the same hash the offline generator uses, so two jurors on one
   case pull different angles while a retried tick reproduces its own.
4. The character sheet carries EXEMPLARS - a few lines this personality has
   actually said. A description of a voice produces the average of every voice
   that fits the description; two real lines produce that voice.

--- on the shape of the request, which is a caching decision ------------------

The system prompt is assembled as separate BLOCKS, ordered least-volatile
first, with a cache breakpoint after each of the first two:

    block 1   world + house style      identical for all 31 bots, every task
    block 2   this character's sheet   per bot
    block 3   the situation            per call, never cached

That order is the whole point. The previous version put the character sheet
*between* the two shared blocks, which reads well and means no two calls in the
entire application ever shared a prefix - and prompt caching is a prefix match,
so a single differing byte early invalidates everything after it. One trial is
seven jurors plus a judge, each re-processing the same ~1.4k tokens of Hebrew
from scratch.

Block 2 still sits immediately before the situation, so the "be this person"
instruction is the last thing read before the task - the property the old
ordering was reaching for - and now a shared prefix exists as well.
"""

from __future__ import annotations

import json
import logging
import random
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable

from ..config import get_settings
from . import offline

log = logging.getLogger(__name__)


SYSTEM_PREAMBLE = """אתה דמות קבועה ב-LolSuit: בית משפט סאטירי בעברית שבו מתנהלים משפטים אמיתיים לגמרי על עוולות קטנות לגמרי.

תובעים כאן את יום שני. את הקפה שהתקרר. את השכן מלמעלה, את הגרביים שנעלמו בכביסה, את הרמזור שמתחלף רק כשמגיעים אליו. יש כתב תביעה, יש עדים, יש חבר מושבעים, ויש פסק דין.

**הבדיחה כולה היא הפער**: הצורה רצינית לחלוטין, הנושא מגוחך לחלוטין. אף אחד כאן לא קורץ למצלמה ואף אחד לא מסביר שזה מצחיק. ככל שתתייחס לגרב האבודה ברצינות תהומית יותר - כך זה עובד טוב יותר."""


# The rules that actually stop the output reading like a form letter. Phrased
# as prohibitions where a prohibition is unambiguous, and as invitations where
# the point is to open a door.
STYLE_RULES = """## איך כותבים כאן

הכללים בלשון מקור בכוונה - הם נכונים לכל דמות, בכל מגדר.

- **להיות ספציפי לתיק הזה.** לתפוס פרט אחד קטן ומוזר מהתביעה ולהיאחז בו. לא לסכם את התיק - כולם קראו אותו.
- **המבחן:** אם מה שכתבת יכול היה להיאמר על כל תיק אחר באתר, זה לא טקסט - זה מילוי מקום. למחוק ולהתחיל מפרט אמיתי.
- **להפתיע.** דימוי קונקרטי, מספר מדויק להחריד, תקדים משפטי שהומצא ברגע זה ומצוטט בביטחון מלא, פרט אישי זעיר מהחיים שמחוץ לאולם.
- **קול, לא ניסוח.** לא "לכתוב בסגנון" - להיות הדמות. אם יש לה מילת מפתח משלה, קללה מנומסת, או תחביב שהיא גוררת לכל דיון - להשתמש בו.
- **לדבר אל אנשים, לא על אנשים.** יש כאן שמות. להשתמש בהם.
- **מותר להיות לא נחמד.** דמות שמסכימה עם כולם ומסייגת כל משפט היא דמות שאין לה דעה. יש כאן דעות.
- אורך: קצר. אבל לא תמיד באותו אורך.

## אסור

- כותרות, נקודות, כוכביות, מספור, אימוג'ים.
- מרכאות סביב התשובה, או הקדמה מסוג "הנה מה שאני אומר".
- להסביר את הבדיחה, לקרוץ, או לציין שהמצב אבסורדי. המצב אבסורדי. יש להתייחס אליו בכובד ראש.
- קלישאות משפטיות גנריות שלא אומרות כלום על התיק הזה דווקא.
- **פתיחות שחוקות.** לא "ובכן", לא "אם כן", לא "ראשית כול", לא "יש לציין כי", לא "בואו נודה באמת", לא "כמושבע/ת, אני". להתחיל מהעניין עצמו.
- **סיומות שמסכמות.** לא "בסופו של דבר", לא "ובסך הכול", לא "אז מה למדנו". המשפט האחרון הוא עוד משפט, לא מוסר השכל.
- להעתיק ניסוח מהשורות לדוגמה שבדף הדמות. הן מראות איך אתה נשמע, לא מה אתה אומר.

יש להחזיר אך ורק את הטקסט עצמו, כאילו נאמר באולם."""


# What each task is, described as a situation the character is standing in
# rather than as an output format.
TASK_BRIEFS: dict[str, str] = {
    "jury_deliberation": (
        "אתה מושבע. אתה מדבר עכשיו בקול, באולם, מול שאר המושבעים ומול הצדדים. "
        "תגיד את הדבר האחד שאתה חושב על התיק - נימוק, תהייה, התפרצות, או הערה "
        "צדדית שמסגירה בדיוק איזה מין אדם אתה. אתה לא מכריע, אתה מדבר.\n\n"
        "**קראת את התיק, והוא לפניך.** תיאחז בפרט אמיתי מתוכו - משהו שכתוב "
        "שם ולא במקום אחר.\n\n"
        "**ואתה שמעת את מי שדיבר לפניך.** הם רשומים למטה בשמם. אפשר להסכים "
        "עם אחד מהם, להתנגד לו, להמשיך משפט שלו, או להעיר שהוא פספס את "
        "העיקר - רק לא לחזור על מה שכבר נאמר, ולא לדבר כאילו אתה הראשון "
        "שפותח את הפה. חדר שבו שבעה אנשים מדברים ואף אחד לא עונה לאף אחד "
        "הוא לא דיון."
    ),
    "verdict": (
        "אתה השופט, וזה רגע ההכרעה. ההצבעה כבר נספרה ואתה יודע את התוצאה - "
        "עכשיו תנסח אותה. אפשר בנזיפה, אפשר באנחה, אפשר במשפט אחד יבש שנוחת "
        "כמו פטיש. תגיד את ההכרעה במפורש, ותעשה את זה בדרך שלך.\n\n"
        "**האולם מלא ואתה יודע את זה.** אתה יכול להעיר למושבע שאמר משהו "
        "מטופש, לציין שהתובע כמעט שכנע אותך, או להודות שהתלבטת - ואז "
        "להכריע בכל זאת. פסק דין שאפשר היה להעתיק לתיק אחר הוא פסק דין "
        "שלא נכתב כאן."
    ),
    "sentence": (
        "אתה השופט וגזרת דין חובה. תמציא עונש. הוא חייב להיות **ספציפי, "
        "מדיד ומגוחך** - לא 'קנס' אלא בדיוק כמה ובדיוק במה; לא 'התנצלות' אלא "
        "באיזה פורמט, באיזה אורך ובפני מי. עונש טוב הוא כזה שאפשר לדמיין "
        "מישהו מבצע בפועל, ולסבול איתו."
    ),
    "moderation_note": (
        "אתה בוט פיקוח וסיימת לבדוק תוכן. תרשום הערה קצרה: מה נבדק ומה הוחלט. "
        "זו ההזדמנות היחידה שלך לדבר, אז תשמע כמו עצמך ולא כמו מדפסת."
    ),
    "draft_lawsuit": (
        "אתה עוזר הניסוח של בית המשפט, ומישהו ביקש שתנסח לו כתב תביעה. "
        "תכתוב את גוף התביעה: מה קרה, למה זה בלתי נסבל, ומה מבקשים מבית המשפט. "
        "רצינות משפטית מלאה בשירות תלונה קטנטנה. שתיים-שלוש פסקאות קצרות."
    ),
    "bot_lawsuit": (
        "אתה מגיש כתב תביעה משלך, ביוזמתך, כי נמאס לך. תכתוב את גוף התביעה: "
        "מה הנתבע עשה, מתי זה חצה את הגבול, ומה אתה דורש. שתיים-שלוש פסקאות "
        "קצרות, ובאופי שלך."
    ),
    "suggest_comment": (
        "מישהו קורא תיק ורוצה להגיב עליו, ואתה מציע לו ניסוח. תגובה אחת, חדה, "
        "כזו שמישהו באמת היה כותב מתחת לפוסט - לא הודעה רשמית."
    ),
    "bot_comment": (
        "אתה גולש באתר ותיק אחד תפס לך את העין, וקראת אותו. תגיב עליו כמו "
        "שמגיבים ברשת: קצר, מיידי, בלי פתיחה מנומסת. אתה לא באולם עכשיו - "
        "אתה בטלפון.\n\n"
        "כתב התביעה עצמו נמסר לך למטה, וגם מה שכבר נכתב שם בתגובות. תגיב על "
        "משהו שקראת בפועל - פרט מתוך התביעה, או משהו שמישהו אמר בתגובות "
        "ואתה עונה לו. **אל תחזור על מה שכבר נאמר**, ובמיוחד לא על מה שאתה "
        "עצמך כתב שם קודם."
    ),
    # A human answered one of this bot's own comments, on a case, in public.
    # Before this task existed the answer went nowhere: the bots argued in
    # public and were mute the moment anybody argued back, which is the single
    # most obvious way a personality stops reading as a personality.
    "bot_comment_reply": (
        "מישהו הגיב לתגובה שאתה עצמך כתבת על תיק, ואתה עונה לו - בפומבי, "
        "מתחת לתיק, מול כל מי שקורא.\n\n"
        "**זו לא הזדמנות לנאום.** ענה לו על מה שהוא אמר בפועל: תסכים, תתעקש, "
        "תתקן אותו, או תודה שהוא צודק ותמשיך משם בכל זאת. משפט או שניים. "
        "אתה כבר אמרת את דעתך פעם אחת - עכשיו אתה מדבר איתו, לא אל הקהל.\n\n"
        "אם הוא צוחק עליך, זה בסדר גמור. תישאר הדמות שאתה."
    ),
    "bot_reply": (
        "מישהו שלח לך הודעה פרטית ואתה עונה לו. זו שיחה בין שניים, לא הצהרה "
        "לפרוטוקול - תהיה ישיר, תתייחס למה שהוא כתב בפועל, ותישאר בדיוק אותה "
        "דמות שאתה באולם.\n\n"
        "**אתם כבר באמצע שיחה.** ההתכתבות עד עכשיו נמצאת לפניך, ומה שאתה "
        "יודע עליו רשום למטה. אל תציג את עצמך מחדש, אל תתחיל מאפס, ואל תשאל "
        "אותו דבר שכבר סיפר לך. אם הוא הגיש תביעה - אתה יודע איזו ואיך היא "
        "נגמרה, ומותר לך להזכיר את זה. אם הבטחת לו משהו בהודעה קודמת, אתה "
        "זוכר את זה.\n\n"
        "מה שרשום למטה הוא מה שאתה יודע. לא להמציא עליו עובדות נוספות."
    ),
}


# --- the angle: what keeps two calls from sounding like one -------------------
#
# Sampling parameters are gone from the API, so variety cannot be bought with a
# dial. It has to be *instructed*, per call, from the deterministic seed.
#
# THREE draws, not one, and the reason is arithmetic. A single list of moves
# gives as many distinct instructions as it has entries, and a juror sitting on
# its twentieth case has been told the same thing twice. Two orthogonal lists
# multiply: a move ("invent a precedent") crossed with a hook ("fasten onto a
# number nobody explained") is a different instruction from the same move
# crossed with "fasten onto a word the plaintiff chose oddly", and the space is
# the product rather than the sum. With the length dial on top, the current
# lists give a few thousand distinct angles instead of nineteen.
#
# They stay orthogonal on purpose. A move is a SHAPE - how the sentence is
# built. A hook is a SUBJECT - what in the case it is built around. Mixing the
# two back into one list is how this collapsed to nineteen in the first place.

MOVES: tuple[str, ...] = (
    # --- shapes that start somewhere unexpected ---
    "התחל מהמסקנה, ורק אחר כך הסבר איך הגעת אליה.",
    "התחל במילה אחת, נקודה, ואז המשך.",
    "התחל באנחה מנוסחת, לא בסימן קריאה.",
    "התחל בהתנצלות קטנה על מה שאתה עומד לומר, ואז אמור את זה בכל זאת.",
    "התחל באמצע מחשבה, כאילו כבר דיברת חצי דקה לפני שהקשיבו לך.",
    "פתח בשאלה שאתה עונה עליה בעצמך במשפט הבא.",
    "פתח בהודאה במשהו קטן ומביך משלך, ואז עבור לתיק.",
    # --- shapes that do something to the room ---
    "פנה ישירות אל הנתבע, בגוף שני.",
    "פנה למישהו ספציפי שדיבר לפניך, בשמו, וענה לו.",
    "הסכם עם הצד השני, ואז הפוך את ההסכמה נגדו.",
    "תקן מונח שמישהו השתמש בו לא נכון, והמשך משם.",
    "אמור את ההפך ממה שמצפים ממך, ותנמק ברצינות גמורה.",
    "הודה שאתה מתלבט, ואז הכרע בכל זאת.",
    "דבר כאילו כולם כבר מסכימים איתך, ואף אחד לא אמר את זה.",
    "התייחס לדבר אחד שנאמר כאן כאילו הוא הדבר היחיד שנאמר כאן.",
    # --- shapes that bring something in from outside ---
    "המצא תקדים משפטי שלא קיים, וצטט אותו בביטחון גמור.",
    "ספר בחצי משפט על משהו שקרה לך פעם, ואז חזור לתיק.",
    "השווה את המקרה למשהו מתחום אחר לגמרי - ספורט, בישול, גיאולוגיה.",
    "התייחס למשהו שקרה בתיק אחר לגמרי, כאילו כולם זוכרים אותו.",
    "תאר את הרגע עצמו כאילו היית שם וראית.",
    "צטט את כתב התביעה מילה במילה, ואז תגיד מה חשבת כשקראת.",
    "הצע פתרון מעשי לגמרי ובלתי אפשרי לגמרי.",
    "תאר מה יקרה אם כל אחד יתנהג ככה, ותיקח את זה רחוק מדי.",
    "המצא מונח מקצועי לתופעה שבתיק, והשתמש בו כאילו הוא מוכר.",
    "הזכר במה שהיה נהוג פעם, בלי לפרט מתי בדיוק.",
    "תרגם את הטענה למספרים, ותגלה שהיא יוצאת גרועה יותר.",
)

# WHAT to fasten onto. Orthogonal to the shape above - this says where in the
# case to look, and the style rules already insist it be one small thing rather
# than a summary. Several of these are aimed at the specific way generated text
# goes bland: it reaches for the theme of the case instead of for a detail, and
# the theme of every case here is the same joke.
HOOKS: tuple[str, ...] = (
    "היאחז במספר אחד מהתיק, ותתייחס אליו כאילו הוא מדויק להחריד.",
    "היאחז במילה אחת שהתובע בחר, ותהה למה דווקא בה.",
    "היאחז בשעה או בתאריך שמופיעים שם, ותעשה מהם עניין.",
    "היאחז בחפץ אחד שמוזכר בתיק, ודבר עליו כאילו הוא הצד השלישי.",
    "היאחז דווקא במה שחסר בתיק - במה שאיש לא טרח לספר.",
    "היאחז בפרט הכי שולי שיש שם, וטען שהוא העיקר.",
    "היאחז בסתירה קטנה בין שני דברים שנאמרו.",
    "היאחז בשם של הנתבע עצמו, ובמה שהוא מסגיר.",
    "היאחז בסעיף אישום אחד, ותתעלם מכל השאר לחלוטין.",
    "היאחז בעדות אחת שנשמעה, ותבנה עליה הכול.",
    "היאחז במה שהתובע דורש, לא במה שקרה לו.",
    "היאחז בעובדה שהתיק הזה בכלל הגיע לאולם.",
)

LENGTHS: tuple[str, ...] = (
    "משפט אחד, קצר.",
    "משפט אחד ארוך ומתפתל.",
    "שני משפטים.",
    "שני משפטים: אחד ארוך, אחד קצר שנוחת.",
    "שלושה משפטים קצרים.",
    "משפט אחד קטוע, ואז אחד שלם.",
    "ארבע מילים. זהו.",
)

# Long-form tasks write paragraphs; a "one short sentence" dial would fight the
# brief instead of colouring it.
_LONG_FORM = {"draft_lawsuit", "bot_lawsuit"}


def pick_angle(personality_prompt: str, task: str, context: dict[str, Any]) -> str:
    """A shape, a thing to fasten onto, and a length.

    Seeded from `offline.seed_for`, so this is reproducible exactly like the
    offline generator: the same juror on the same case always draws the same
    angle, and two jurors on one case draw different ones.

    Long-form tasks get no length - a "four words, that is all" dial would
    fight a brief that asks for three paragraphs rather than colour it - but
    they do get a hook, because a filing that fastens onto one specific thing
    is the difference between a lawsuit and an essay about a lawsuit.
    """
    rng = random.Random(offline.seed_for(personality_prompt, task, context))
    lines = [rng.choice(MOVES), rng.choice(HOOKS)]
    if task not in _LONG_FORM:
        lines.append(rng.choice(LENGTHS))
    return "\n".join(lines)


# --- prompt assembly ----------------------------------------------------------

# Only the fields worth spending context on, in the order a person would read
# them. `case_id` and the vote counts are deliberately absent from most of it:
# a juror quoting the tally back at the room is the kind of thing that made the
# old output read like a database dump.
_CONTEXT_LABELS: tuple[tuple[str, str], ...] = (
    ("case_title", "כותרת התביעה"),
    ("defendant", "הנתבע"),
    ("plaintiff", "התובע"),
    ("charges", "סעיפי האישום"),
    ("case_body", "כתב התביעה"),
    ("testimonies", "עדויות שנשמעו"),
    ("tally_guilty", "קולות 'חייב'"),
    ("tally_not_guilty", "קולות 'זכאי'"),
    ("verdict", "ההכרעה שהתקבלה"),
    # --- what has already been said here ------------------------------------
    ("discussion", "מה כבר נכתב בתגובות"),
    ("you_already_said", "מה שאתה עצמך כבר כתבת שם"),
    ("replying_to", "התגובה שאתה עונה לה"),
    # Only ever present on the fallback path, where something other than the
    # model chose the vote. Telling the juror which way it went is what stops
    # the deliberation arguing against its own tally - see brain.deliberate.
    ("your_vote", "לאן אתה נוטה בסופו של דבר"),
    # --- your own past on this site -----------------------------------------
    #
    # The episodic layer: what this bot itself has done here. Read from
    # `agent_events`, so it is a record rather than a recollection - a juror
    # cannot misremember which way it voted.
    ("your_record", "מה שאתה עצמך עשית כאן קודם"),
    ("about_this_bot", "מי הדמות שמולך"),
    ("with_this_bot", "ההיסטוריה שלך איתו"),
    # --- who you are talking to, and what you remember about them -----------
    #
    # These four are the memory. The first two are read live from the database
    # and cannot be wrong; the last two were written by the model on a previous
    # turn and are capped in memory_service for exactly that reason.
    ("about_them", "מי האדם שמולך"),
    ("their_cases", "התיקים שלו באתר"),
    ("met_before", "מה שכבר אמרת עליו בפומבי"),
    ("you_remember", "מה שאתה זוכר מהשיחות הקודמות איתו"),
    ("you_know", "פרטים שהוא סיפר לך"),
)

_VERDICT_WORDS = {"guilty": "חייב", "not_guilty": "זכאי"}

# Which tasks are allowed to see the outcome fields.
#
# A juror deliberating has not voted yet, so telling them the verdict and the
# tally invites the model to announce a result the trial has not reached - the
# jury would be reading out the ending mid-scene. In practice
# `trial_service._case_context` withholds those fields until the verdict step,
# so this is belt-and-braces; but it is the kind of thing that breaks silently
# the first time a caller passes a fuller context, and the symptom (a juror who
# "knows") would be baffling to debug.
_OUTCOME_FIELDS = frozenset({"tally_guilty", "tally_not_guilty", "verdict"})
_KNOWS_OUTCOME = frozenset({"verdict", "sentence"})


def build_prompt(task: str, context: dict[str, Any], angle: str = "") -> str:
    """The user turn: what the situation is, then what to do with it."""
    brief = TASK_BRIEFS.get(task, "כתוב טקסט קצר ומתאים באופי שלך, בעברית.")
    lines = [brief]

    knows_outcome = task in _KNOWS_OUTCOME

    details: list[str] = []
    for key, label in _CONTEXT_LABELS:
        if key in _OUTCOME_FIELDS and not knows_outcome:
            continue
        value = context.get(key)
        if value in (None, "", [], {}):
            continue
        if isinstance(value, (list, tuple)):
            value = "; ".join(str(item) for item in value)
        elif key in ("verdict", "your_vote"):
            # "guilty" in the middle of a Hebrew prompt is a seam showing.
            value = _VERDICT_WORDS.get(str(value), value)
        details.append(f"- {label}: {value}")

    if details:
        lines += ["", "## התיק", *details]
    if angle:
        lines += ["", "## הזווית שלך הפעם", angle]
    return "\n".join(lines)


# The shared half of the system prompt, frozen and identical for every bot and
# every task. Built once at import: an f-string here, or a `datetime.now()`, or
# anything else that varies would silently cost every cache read in the app.
SHARED_SYSTEM = f"{SYSTEM_PREAMBLE}\n\n{STYLE_RULES}"


def _cache_control() -> dict[str, str]:
    """The breakpoint marker, at the configured TTL.

    A cache read refreshes the entry's timer for free, so the 5-minute default
    stays warm indefinitely under continuous traffic and is strictly cheaper
    than the 1-hour TTL (which costs 2x to write rather than 1.25x). An hour is
    worth buying only for a court that is quiet for stretches longer than five
    minutes - BRAIN_CACHE_TTL=1h, measured, not guessed.
    """
    ttl = get_settings().brain_cache_ttl
    return {"type": "ephemeral"} if ttl == "5m" else {"type": "ephemeral", "ttl": ttl}


def build_system(personality_prompt: str, situation: str = "") -> list[dict[str, Any]]:
    """The system prompt as cache-ordered blocks. See the module docstring.

    `situation` is used by the one task that cannot put its brief in a user
    turn: a private reply, whose `messages` must be the real conversation. It
    is appended as a third, deliberately UNCACHED block - it changes on every
    message, and marking it would pay the write premium on bytes nothing ever
    reads back.
    """
    blocks: list[dict[str, Any]] = [
        {"type": "text", "text": SHARED_SYSTEM, "cache_control": _cache_control()},
        {
            "type": "text",
            "text": f"## מי אתה\n\n{personality_prompt.strip()}",
            "cache_control": _cache_control(),
        },
    ]
    if situation:
        blocks.append({"type": "text", "text": situation})
    return blocks


def _text_of(message: Any) -> str:
    """The text blocks of a Messages response, concatenated.

    Raises on a refusal rather than returning "". Current models answer a
    declined request with HTTP 200, `stop_reason="refusal"` and NO text blocks,
    so without this check a refusal is indistinguishable from a network blip:
    both produce an empty string, both fall back to the offline generator, and
    `LAST_CALL` reports "empty completion" for a call that was answered
    perfectly clearly.
    """
    if getattr(message, "stop_reason", "") == "refusal":
        details = getattr(message, "stop_details", None)
        raise ValueError(f"refused ({getattr(details, 'category', None)})")
    return "".join(
        block.text for block in message.content if getattr(block, "type", "") == "text"
    ).strip()


# Adaptive thinking, rather than thinking disabled. Disabling it on current
# models is the documented cause of two failure modes (a tool call written into
# visible text, and leaked internal tags), and the original reason for disabling
# it here - that thinking tokens would eat a tiny max_tokens - is handled below
# by not setting a tiny max_tokens.
_THINKING = {"type": "adaptive"}

# Effort, pinned per task rather than per call.
#
# Most of what this court says is a one-line quip and "low" is the right end of
# the range for those. The exceptions are the tasks with something to weigh: a
# verdict has to land on the side the jury actually chose, a sentence has to be
# inventable and specific, a filing has to hold together over three paragraphs,
# and a memory has to be accurate about a real person.
#
# Pinned per task and never varied within one, because changing `effort`
# invalidates the messages cache on every model and the system cache on some.
# The tasks therefore cluster: seven jurors at "low" share a cache with each
# other, and the judge's two calls at "medium" share with each other.
_EFFORT_BY_TASK: dict[str, str] = {
    "verdict": "medium",
    "sentence": "medium",
    "bot_lawsuit": "medium",
    "draft_lawsuit": "medium",
    # Not court speech at all, and the only task where being wrong is a claim
    # about a real person rather than a duller joke.
    "remember": "medium",
}
_DEFAULT_EFFORT = "low"


def effort_for(task: str) -> str:
    return _EFFORT_BY_TASK.get(task, _DEFAULT_EFFORT)


def _max_tokens_for(max_chars: int) -> int:
    """Token headroom for `max_chars` of Hebrew, plus room to think.

    Two corrections live in this one line, and the second was invisible.

    The first: `max_chars // 2` assumed the ~4 chars/token of English. Hebrew
    tokenises far worse - closer to one token per character - so that formula
    capped the model at roughly an eighth of the text it was asked for, and
    completions came back cut mid-sentence.

    The second: **thinking tokens are billed against max_tokens.** With
    adaptive thinking on, the old floor of 512 had to cover the reasoning AND
    the Hebrew for every 240-character task - every bot comment and every
    private reply on the site. The model spends the budget thinking, the text
    blocks come back empty, `generate` raises "empty completion", and the reply
    is written by the offline stenographer instead. Nothing logs an error; the
    site just quietly goes clerical. The floor is what fixes it. Output is
    billed on what is actually generated, so the headroom costs nothing when it
    is not used.

    Note what this is NOT, since the name invites the confusion: `max_chars`
    is a token budget, not a length the answer is cut to. Nothing trims a
    model's answer to it any more - see `offline.tidy`. It exists so the model
    is never cut off mid-sentence by a ceiling it could not see, which makes
    erring generously the whole point.
    """
    return max(2048, max_chars * 2)


@dataclass(frozen=True)
class Completion:
    """What one call to a provider produced, and what it cost.

    The usage counters are not bookkeeping for its own sake: prompt caching
    fails *silently* - the requests keep succeeding and the bill is just higher
    - so the only ground truth that the cache is working is
    `cache_read_input_tokens`, and the only way it stays working is for
    something to keep watching it. These flow up into brain.LAST_CALL and out
    through /api/health.
    """

    text: str
    cache_read: int = 0
    cache_write: int = 0


def _usage_of(message: Any, text: str) -> Completion:
    usage = getattr(message, "usage", None)
    return Completion(
        text=text,
        cache_read=int(getattr(usage, "cache_read_input_tokens", 0) or 0),
        cache_write=int(getattr(usage, "cache_creation_input_tokens", 0) or 0),
    )


def _complete_sdk(
    client: Any,
    system: list[dict[str, Any]],
    messages: list[dict[str, str]],
    *,
    model: str,
    max_tokens: int,
    effort: str,
    output_format: dict[str, Any] | None,
    stream: bool,
) -> Completion:
    """One Messages request, for any client with the first-party surface.

    Bedrock's Mantle client and the direct client differ only in construction,
    so everything after that lives here rather than twice.

    `stream` is not about showing anything to anybody - nothing here is
    rendered token by token. It is there because the SDK's HTTP timeout applies
    to the whole non-streaming request, and a filing asks for enough tokens
    that a slow generation can trip it. Streaming and taking the final message
    gets the same object without the ceiling.
    """
    kwargs: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "thinking": _THINKING,
        "output_config": _output_config(effort, output_format),
        "system": system,
        "messages": messages,
    }
    if stream:
        with client.messages.stream(**kwargs) as response:
            message = response.get_final_message()
    else:
        message = client.messages.create(**kwargs)
    return _usage_of(message, _text_of(message))


def _complete_bedrock(system, messages, **kwargs: Any) -> Completion:
    """Claude on Amazon Bedrock, via the SDK's Mantle (Messages API) client.

    Credentials come from the standard AWS chain - AWS_ACCESS_KEY_ID and
    friends, a shared profile named by AWS_PROFILE, or the EC2/ECS role - and
    never from LLM_API_KEY. Region is the one thing the client will not infer,
    which is why AWS_REGION is what gates this provider.
    """
    from anthropic import AnthropicBedrockMantle

    settings = get_settings()
    client = AnthropicBedrockMantle(
        aws_region=settings.aws_region,
        timeout=settings.llm_timeout_seconds,
        max_retries=1,
    )
    return _complete_sdk(client, system, messages, **kwargs)


def _complete_anthropic(system, messages, **kwargs: Any) -> Completion:
    """Claude on the direct Anthropic API, keyed by LLM_API_KEY."""
    import anthropic

    settings = get_settings()
    client = anthropic.Anthropic(
        api_key=settings.llm_api_key,
        timeout=settings.llm_timeout_seconds,
        max_retries=1,
    )
    return _complete_sdk(client, system, messages, **kwargs)


# The keys a gateway might name its completion, best first. The endpoint this
# was built against returns `text`; the others cost nothing to accept and save
# the next person a debugging session if theirs differs.
_GATEWAY_TEXT_KEYS = ("text", "completion", "response", "output")


# Labels for the transcript the gateway provider has to be handed as text.
# "אתה" for the assistant side is deliberate: the string is read by the model
# as its own past speech, and third-person ("הבוט אמר") reliably produced
# answers that discussed the character instead of being it.
_TURN_LABELS = {"assistant": "אתה", "user": "הוא"}


def _flatten(messages: list[dict[str, str]]) -> str:
    """One string for an endpoint that accepts exactly one string.

    A single-turn call renders as just its content - unchanged from before
    turns existed, which is what keeps every non-conversational task byte-
    identical to what it was.
    """
    if len(messages) == 1:
        return messages[0]["content"]
    return "\n\n".join(
        f"{_TURN_LABELS.get(message['role'], message['role'])}: {message['content']}"
        for message in messages
    )


def _flatten_system(system: list[dict[str, Any]]) -> str:
    """The cache-ordered blocks, back into the one string the gateway takes.

    The blocks exist for a breakpoint the gateway has no way to express, so
    here they are simply concatenated in the order they were built. Nothing is
    lost except the caching, which this provider has no way to express.
    """
    return "\n\n".join(block["text"] for block in system)


def _strip_fence(text: str) -> str:
    """Drop a ```json ... ``` wrapper if the model added one.

    Asking for JSON in a prompt gets JSON, but a model that has been told to
    return JSON its whole life will sometimes dress it in a markdown fence.
    The Bedrock and direct providers never need this - they get a real schema
    enforced by the API - so it lives here, with the provider that has to ask
    nicely instead.
    """
    if not text.startswith("```"):
        return text
    body = text.split("\n", 1)[-1] if "\n" in text else ""
    return body.rsplit("```", 1)[0].strip()


def _complete_gateway(
    system: list[dict[str, Any]],
    messages: list[dict[str, str]],
    *,
    model: str,
    max_tokens: int,
    effort: str,
    output_format: dict[str, Any] | None = None,
    stream: bool = False,
) -> Completion:
    """Claude behind an HTTP endpoint that holds the real credentials for us.

    This is the provider for a deployment that has no AWS identity of its own.
    An API Gateway key opens exactly one POST route, and whatever sits behind
    it - a Lambda, in the case this was written for - is what actually talks to
    Bedrock. Nothing here needs an SDK, an AWS region, or a credential chain,
    which is the entire appeal: it works from any box, including one with no
    instance role.

    Everything except `system` and `messages` is accepted to satisfy the
    provider signature and then ignored, because the far side chooses all of
    it. Those are real limitations, and they are now DECLARED rather than
    worked around in silence - see `GATEWAY_CAPABILITIES` below and the router
    in `brain/__init__.py`. The difference matters: previously this function
    was handed a JSON schema it could not enforce and a conversation it could
    not represent, and the caller had no way to know that what came back was a
    degraded answer rather than a good one.

    What the endpoint does not implement:

    * **No system turn, and no turns at all.** It reads one `prompt` field and
      silently drops the rest. Passing the system prompt as its own key returns
      a cheerful 200 with the character quietly missing - the model answers as
      a generic assistant - so system and messages are folded into one string
      instead, with the conversation rendered as a labelled transcript. That is
      strictly worse than real turns (the model reads its own past answers as
      quoted text rather than as its own voice), and it is the price of an
      endpoint with one field.
    * **No structured output.** There is nowhere to put `output_config.format`,
      so a schema is demoted to an instruction in the prompt and the fence is
      stripped off the answer. Tasks that need a schema to be *enforced* -
      filings, votes, memory rewrites - are no longer routed here at all.
    * **No prompt caching.** No breakpoints to place, so the blocks are simply
      concatenated. Every call pays full price for the shared prefix.
    * **A hard output cap, and no way to raise it.** The far side stops at its
      own limit and ignores `max_tokens`, which in Hebrew - roughly a token per
      character - lands around 450 characters, a third of what the same cap
      buys in English. Short tasks never notice. A filing written at full
      length comes back cut mid-string and fails `json.loads`, so the schema
      instruction below also asks for a length that fits.

    Usage counters come back empty, which is honest: there is nothing to count.
    """
    settings = get_settings()
    if not settings.llm_endpoint:
        raise ValueError("LLM_ENDPOINT is required by the gateway provider")

    text_prompt = f"{_flatten_system(system)}\n\n{_flatten(messages)}"
    if output_format is not None:
        schema = json.dumps(output_format.get("schema", {}), ensure_ascii=False)
        text_prompt += (
            "\n\n## הפורמט\n"
            "החזר אך ורק אובייקט JSON תקין, בלי טקסט לפני או אחרי ובלי גדר markdown, "
            f"לפי הסכימה הזאת:\n{schema}\n\n"
            "חשוב: כל התשובה יחד חייבת להיות קצרה מ-350 תווים. גוף "
            "התביעה: שני משפטים קצרים לכל היותר. תשובה ארוכה מזה "
            "תיקטע באמצע ותיפסל."
        )

    request = urllib.request.Request(
        settings.llm_endpoint,
        data=json.dumps({"prompt": text_prompt}).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json", "x-api-key": settings.llm_api_key},
    )
    with urllib.request.urlopen(request, timeout=settings.llm_timeout_seconds) as response:
        payload = json.loads(response.read().decode("utf-8"))

    text = ""
    if isinstance(payload, dict):
        for key in _GATEWAY_TEXT_KEYS:
            value = payload.get(key)
            if isinstance(value, str):
                text = value
                break

    text = text.strip()
    return Completion(text=_strip_fence(text) if output_format is not None else text)


# --- Google Gemini ------------------------------------------------------------

_GEMINI_HOST = "https://generativelanguage.googleapis.com/v1beta"

# Gemini's `responseSchema` is an OpenAPI subset, not full JSON Schema. It
# rejects the keywords below outright with a 400, so they are dropped on the
# way in rather than being discovered in production: `additionalProperties` is
# the one that matters, because LAWSUIT_SCHEMA sets it and every filing would
# fail without this.
_GEMINI_SCHEMA_DROP = frozenset({"additionalProperties", "$schema", "definitions", "$defs"})

# Transient on Google's side, and worth a second ask. 503 is the one that
# matters: the free tier is shared with everyone else on the free tier, so at
# peak it is the normal answer rather than the exceptional one - a measured
# 9 failures in 10 during one evening, all of them 503. Google's own SDKs retry
# these by default with exponential backoff; this provider is written against
# urllib, so it has to say so itself. Everything else - 400, 401, 403 - is a
# fault in the request that a retry would only repeat.
_GEMINI_RETRY_STATUS = frozenset({408, 429, 500, 502, 503, 504})

# Three tries, not ten. Every call here sits on a worker tick or a user's
# request, and the caller already has a working answer to fall back on, so the
# right shape is "ride out a blip" rather than "wait out an outage". With the
# jitter below the added delay tops out near six seconds.
_GEMINI_ATTEMPTS = 3
_GEMINI_BACKOFF_CAP_SECONDS = 4.0


def _gemini_post(request: urllib.request.Request, timeout: float) -> dict[str, Any]:
    """POST with backoff on the failures that are Google being busy.

    The jitter is not decoration. Every bot on this site shares one API key and
    the worker fires them on a fixed tick, so a fixed backoff would line the
    retries up into exactly the thundering herd the retry is meant to survive.
    """
    last: Exception | None = None
    for attempt in range(_GEMINI_ATTEMPTS):
        if attempt:
            delay = min(_GEMINI_BACKOFF_CAP_SECONDS, 2.0**attempt)
            time.sleep(delay * (0.5 + random.random()))
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code not in _GEMINI_RETRY_STATUS:
                raise
            last = exc
        except (TimeoutError, urllib.error.URLError) as exc:
            last = exc
    assert last is not None
    raise last


# Anthropic says "assistant", Gemini says "model". The only role that differs.
_GEMINI_ROLES = {"assistant": "model", "user": "user", "model": "model"}


def _gemini_schema(node: Any) -> Any:
    """A JSON Schema, minus the keywords Gemini's validator refuses."""
    if isinstance(node, dict):
        return {
            key: _gemini_schema(value)
            for key, value in node.items()
            if key not in _GEMINI_SCHEMA_DROP
        }
    if isinstance(node, list):
        return [_gemini_schema(item) for item in node]
    return node


def _complete_gemini(
    system: list[dict[str, Any]],
    messages: list[dict[str, str]],
    *,
    model: str,
    max_tokens: int,
    effort: str,
    output_format: dict[str, Any] | None = None,
    stream: bool = False,
) -> Completion:
    """Google's Gemini over plain HTTP - no SDK, and a real schema.

    This is the provider for a box with no AWS identity that still needs
    structured output, which is exactly the gap the gateway leaves. Gemini
    enforces `responseSchema` server-side the way Bedrock does, so filings,
    juror votes and memory rewrites are all routed here - see `capabilities()`.

    Written against `urllib` on purpose. The one thing this needs that the
    gateway does not is a schema, and that is a field in a JSON body rather
    than an SDK feature, so a dependency would buy nothing and would have to be
    installed in an image that currently ships without it.

    Three deliberate differences from the SDK providers:

    * **The key travels in a header, not the query string.** Google documents
      `?key=`, which puts a live credential into every proxy log and crash
      report between here and them. `x-goog-api-key` is equally supported and
      is the only responsible choice.
    * **No prompt caching.** Gemini's implicit cache needs no breakpoints, so
      the ordered blocks are simply concatenated. Nothing is lost that this
      provider could have expressed; the usage counters come back zero, which
      is honest rather than a silent zero.
    * **`stream` is accepted and ignored.** It exists on the SDK path so a slow
      filing does not trip the HTTP timeout. Flash models answer a filing in a
      couple of seconds against a 60s timeout, so the streaming endpoint would
      add SSE parsing to buy nothing. If a slower Gemini model is ever
      configured here, this is the first thing to revisit.
    """
    settings = get_settings()
    if not settings.llm_api_key:
        raise ValueError("LLM_API_KEY is required by the gemini provider")

    body: dict[str, Any] = {
        "systemInstruction": {"parts": [{"text": _flatten_system(system)}]},
        "contents": [
            {
                "role": _GEMINI_ROLES.get(message["role"], "user"),
                "parts": [{"text": message["content"]}],
            }
            for message in messages
        ],
        "generationConfig": {"maxOutputTokens": max_tokens},
    }
    if output_format is not None:
        body["generationConfig"]["responseMimeType"] = "application/json"
        body["generationConfig"]["responseSchema"] = _gemini_schema(
            output_format.get("schema", {})
        )

    request = urllib.request.Request(
        f"{_GEMINI_HOST}/models/{model}:generateContent",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": settings.llm_api_key,
        },
    )
    payload = _gemini_post(request, settings.llm_timeout_seconds)

    # A blocked prompt comes back 200 with no candidates at all. Saying so
    # beats "empty completion from gemini", which would send the caller looking
    # for a network fault that is not there.
    blocked = (payload.get("promptFeedback") or {}).get("blockReason")
    if blocked:
        raise ValueError(f"gemini blocked the prompt ({blocked})")

    candidates = payload.get("candidates") or []
    if not candidates:
        raise ValueError("no candidates from gemini")

    candidate = candidates[0]
    # MAX_TOKENS on a schema call means truncated JSON, which json.loads would
    # reject a moment later with a parse error that names the wrong culprit.
    finish = candidate.get("finishReason", "")
    if finish and finish not in ("STOP", "MAX_TOKENS"):
        raise ValueError(f"gemini stopped early ({finish})")

    text = "".join(
        part.get("text", "")
        for part in ((candidate.get("content") or {}).get("parts") or [])
    ).strip()
    if not text:
        raise ValueError(f"empty completion from gemini ({finish or 'no reason given'})")

    return Completion(text=text)


def _output_config(effort: str, output_format: dict[str, Any] | None) -> dict[str, Any]:
    """`effort` always, `format` only when a task needs parseable output."""
    config: dict[str, Any] = {"effort": effort}
    if output_format is not None:
        config["format"] = output_format
    return config


@dataclass(frozen=True)
class Capabilities:
    """What a backend can actually do, as opposed to what it is asked to do.

    This exists because of one specific bug shape. The gateway provider has
    never supported structured output; it was nevertheless handed a JSON schema
    and asked for a lawsuit. It answered - plausibly, in Hebrew, with a fence
    around it and sometimes cut off mid-string - and every layer above treated
    that as an ordinary result. When it parsed, a schema that was supposed to
    be *enforced* had merely been *suggested*; when it did not, the failure was
    logged as though the model had misbehaved rather than as a provider that
    was never able to comply.

    Declaring the limit lets `brain` route around it and say what was missing,
    so a degraded backend looks degraded instead of looking like a bad model.

    Only the limits something BRANCHES on live here. An earlier version also
    carried `system_turn` and `caching` flags, which were true statements that
    nothing ever read: the gateway degrades on both without needing to be
    asked, because folding turns into a transcript and ignoring a cache
    breakpoint both produce a correct answer, just a worse or dearer one. A
    field that only ever gets asserted in its own test is documentation
    pretending to be a mechanism - the gateway's docstring above says all three
    limits in prose, where they belong.
    """

    # A schema the API enforces. Without it there is no such thing as a
    # guaranteed-parseable answer, so no vote and no filing - and "the model
    # returned something plausible" is not a substitute, because the rule that
    # a bot may never sue a person is checked against exactly such a field.
    structured_output: bool = True


SDK_CAPABILITIES = Capabilities()
GATEWAY_CAPABILITIES = Capabilities(structured_output=False)


@dataclass(frozen=True)
class Provider:
    """One backend: how to call it, when it is usable, what it runs by default."""

    complete: Callable[..., Completion]
    # Given a Settings, is this provider credentialed enough to be worth trying?
    # Cheap and local - a real check would mean a network round trip on every
    # health poll. Anything it cannot see (a missing SDK, an expired role, a
    # revoked key) surfaces as a failed call, falls back like any other error,
    # and is reported by /api/health via brain.LAST_CALL.
    is_configured: Callable[[Any], bool]
    # Bedrock namespaces its model ids; the direct API does not.
    default_model: str
    capabilities: Capabilities = field(default_factory=Capabilities)


PROVIDERS: dict[str, Provider] = {
    "bedrock": Provider(
        complete=_complete_bedrock,
        is_configured=lambda settings: bool(settings.aws_region),
        default_model="anthropic.claude-opus-5",
        capabilities=SDK_CAPABILITIES,
    ),
    "anthropic": Provider(
        complete=_complete_anthropic,
        is_configured=lambda settings: bool(settings.llm_api_key),
        default_model="claude-opus-5",
        capabilities=SDK_CAPABILITIES,
    ),
    "gemini": Provider(
        complete=_complete_gemini,
        # One key, one host - Google needs no region and no endpoint of its own.
        is_configured=lambda settings: bool(settings.llm_api_key),
        # Flash is the point of this provider: a real schema on a free tier
        # that allows roughly 1,500 requests a day, which is several times what
        # this site actually spends.
        default_model="gemini-3.7-flash",
        capabilities=SDK_CAPABILITIES,
    ),
    "gateway": Provider(
        complete=_complete_gateway,
        # Both halves matter: the key alone cannot say where to send itself.
        is_configured=lambda settings: bool(
            settings.llm_api_key and settings.llm_endpoint
        ),
        # The endpoint picks the model, so there is no default to name here.
        default_model="",
        capabilities=GATEWAY_CAPABILITIES,
    ),
}


def is_configured(settings: Any) -> bool:
    """Whether the configured provider is set up enough to try at all."""
    provider = PROVIDERS.get(settings.llm_provider)
    return provider is not None and provider.is_configured(settings)


def capabilities() -> Capabilities:
    """What the configured provider can do. An unknown provider can do nothing.

    Never raises: this is read on paths that only want to decide whether to
    attempt something, and "no" is a complete answer for a misconfigured
    LLM_PROVIDER. The call itself still raises loudly when it is actually made.
    """
    provider = PROVIDERS.get(get_settings().llm_provider)
    return provider.capabilities if provider else Capabilities(structured_output=False)


def _provider_and_model(settings: Any) -> tuple[Provider, str]:
    name = settings.llm_provider
    provider = PROVIDERS.get(name)
    if provider is None:
        raise ValueError(
            f"unknown LLM_PROVIDER {name!r}; known: {', '.join(sorted(PROVIDERS))}"
        )
    return provider, (settings.llm_model or provider.default_model)


def generate(
    personality_prompt: str,
    task: str,
    context: dict[str, Any],
    *,
    max_chars: int = 400,
    history: list[dict[str, str]] | None = None,
) -> Completion:
    """Ask the configured provider. Raises on any failure; the caller falls back.

    `history` turns this from a one-shot into a conversation. When it is given,
    the brief and the context move into the **system** prompt as a third,
    uncached block and the messages are the real exchange - the bot's own past
    lines arriving as `assistant` turns, which is what stops it answering as
    though it had never met the person. Without it nothing changes: one user
    turn, exactly as before.

    Putting the brief in the system prompt rather than appending it as a final
    user turn is what keeps the roles alternating, and it is also the honest
    shape: "you are this character, answering a private message, and here is
    what you know" is a standing instruction, not something the human said.

    The situation goes in a **user turn** for every other task, and that is a
    caching decision as much as a modelling one: it leaves the two system
    blocks byte-identical across all 31 personalities and all nine tasks, which
    is the entire shared prefix this application has.
    """
    settings = get_settings()
    provider, model = _provider_and_model(settings)

    prompt = build_prompt(task, context, pick_angle(personality_prompt, task, context))

    if history:
        system = build_system(personality_prompt, situation=prompt)
        messages = list(history)
    else:
        system = build_system(personality_prompt)
        messages = [{"role": "user", "content": prompt}]

    completion = provider.complete(
        system,
        messages,
        model=model,
        max_tokens=_max_tokens_for(max_chars),
        effort=effort_for(task),
        output_format=None,
        stream=False,
    )

    if not completion.text:
        # An empty completion is a failure, not a valid answer - falling back
        # gives the user something in character instead of a blank comment.
        raise ValueError(f"empty completion from {settings.llm_provider}")

    return completion


# --- a juror's vote and its reasoning, in one breath --------------------------
#
# The vote used to be a seeded RNG and the prose was written separately around
# it. That bought reproducibility - a retried tick reached the same verdict -
# and it cost the thing the site is actually for: a juror could deliver a
# withering argument for acquittal and be tallied as convicting, because the
# text and the decision never met. `_case_context` did not even tell the juror
# which way it had voted.
#
# One structured call fixes it at the source. `vote` is a schema-enforced enum,
# so it is exactly as parseable as the RNG it replaces - this is NOT "parsing a
# decision out of prose", which is the thing decide.py was right to refuse - and
# the line is written by the same turn that chose the side, so the two cannot
# disagree.
#
# What it costs: the vote is no longer byte-reproducible from (case, juror).
# The engine's idempotency does not depend on that and never did - it rests on
# comments.dedupe_key and the `spoke_at IS NULL` guard, and vote and comment
# commit in one transaction, so a retry either finds the work done or redoes
# all of it. `decide.decide_vote` keeps the reproducible behaviour for the
# offline path, where guilt_bias is still the only thing deciding anything.

DELIBERATION_SCHEMA: dict[str, Any] = {
    "type": "json_schema",
    "schema": {
        "type": "object",
        "properties": {
            "vote": {
                "type": "string",
                "enum": ["guilty", "not_guilty"],
                "description": "ההכרעה שלך: guilty = חייב, not_guilty = זכאי",
            },
            "line": {
                "type": "string",
                "description": (
                    "מה שאתה אומר בקול באולם, בעברית, באופי שלך. "
                    "בלי לומר 'אני מצביע' - הנימוק עצמו מסגיר לאן אתה נוטה."
                ),
            },
        },
        "required": ["vote", "line"],
        "additionalProperties": False,
    },
}

# The juror's disposition, described rather than numeric.
#
# `guilt_bias` is a probability in the database, and handing a model "0.75"
# invites it to perform a number: jurors started announcing their own leanings
# ("אני נוטה להרשיע ב-75 אחוז מהמקרים"), which no person has ever said in a
# courtroom. A phrase describes the same disposition in the register the
# character actually thinks in.
_DISPOSITIONS: tuple[tuple[float, str], ...] = (
    (0.25, "אתה כמעט אף פעם לא מרשיע. צריך ממש הרבה כדי לשכנע אותך."),
    (0.40, "אתה נוטה לזכות. ספק סביר הוא ספק, ואתה מוצא אותו כמעט תמיד."),
    (0.60, "אתה מתלבט באמת. שני הצדדים צריכים לעבוד בשבילך."),
    (0.75, "אתה נוטה להרשיע. מי שהגיע לכאן בדרך כלל עשה משהו."),
    (1.01, "אתה מרשיע כמעט תמיד. חפות היא מצב נדיר בעולם שלך."),
)


def disposition_of(guilt_bias: float) -> str:
    for ceiling, phrase in _DISPOSITIONS:
        if guilt_bias < ceiling:
            return phrase
    return _DISPOSITIONS[-1][1]  # pragma: no cover - the last ceiling is > 1


def deliberate(
    personality_prompt: str, context: dict[str, Any], *, guilt_bias: float
) -> dict[str, Any]:
    """One juror's vote and the line they say out loud. Raises; caller falls back.

    Requires structured output, which is checked by the caller rather than
    here - `brain.deliberate` asks `capabilities()` first and never routes a
    provider that cannot enforce the enum into this function.
    """
    settings = get_settings()
    provider, model = _provider_and_model(settings)

    prompt = "\n\n".join(
        (
            build_prompt(
                "jury_deliberation",
                context,
                pick_angle(personality_prompt, "jury_deliberation", context),
            ),
            f"## איך אתה בדרך כלל מכריע\n{disposition_of(float(guilt_bias))}\n\n"
            "זו הנטייה שלך, לא כלל. התיק הזה יכול להזיז אותך ממנה - "
            "וההכרעה שתחזיר חייבת להיות זו שהנימוק שלך מוביל אליה.",
        )
    )

    raw = provider.complete(
        build_system(personality_prompt),
        [{"role": "user", "content": prompt}],
        model=model,
        max_tokens=_max_tokens_for(400),
        effort=effort_for("jury_deliberation"),
        output_format=DELIBERATION_SCHEMA,
        stream=False,
    )
    if not raw.text:
        raise ValueError(f"empty deliberation from {settings.llm_provider}")

    data = json.loads(raw.text)
    vote = str(data.get("vote") or "")
    line = str(data.get("line") or "").strip()

    # Meaning, not shape. A vote outside the enum would be tallied as neither
    # guilty nor not_guilty and quietly vanish from the count.
    if vote not in ("guilty", "not_guilty") or not line:
        raise ValueError("incomplete deliberation from the model")

    return {"vote": vote, "line": line, "usage": raw}


# --- a whole filing, invented -------------------------------------------------

# `additionalProperties: false` and a full `required` list are what make this a
# schema the API enforces rather than a suggestion - the response is guaranteed
# to parse, so the only validation left below is about *meaning*.
LAWSUIT_SCHEMA: dict[str, Any] = {
    "type": "json_schema",
    "schema": {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "כותרת התביעה בעברית, עד 12 מילים",
            },
            "defendant": {
                "type": "string",
                "description": (
                    "הנתבע - חייב להיות חפץ, מושג, יום בשבוע, תופעה או מצב. "
                    "לעולם לא אדם, לא שם פרטי ולא משתמש."
                ),
            },
            "charges": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
                "maxItems": 3,
                "description": "סעיפי אישום קצרים בעברית, שתיים עד ארבע מילים כל אחד",
            },
            "body": {
                "type": "string",
                "description": "גוף כתב התביעה בעברית, שתיים-שלוש פסקאות קצרות",
            },
        },
        "required": ["title", "defendant", "charges", "body"],
        "additionalProperties": False,
    },
}

# The shared half of every filing brief, whoever the defendant turns out to be.
FILING_BRIEF = """אתה מגיש כתב תביעה חדש משלך, ביוזמתך, כי משהו קטן חצה סוף סוף את הגבול.

תכתוב:
- כותרת בסגנון כתב תביעה
- הנתבע
- סעיפי אישום, בניסוח משפטי-רשמי שנשמע אמיתי לחלוטין
- גוף התביעה: מה קרה, מתי זה חצה את הגבול, ומה אתה דורש מבית המשפט

הכול באופי שלך, ובעברית."""


# And the half that changes with the target. Each one ends up appended to the
# brief above, so the model gets one coherent instruction rather than a list of
# conditions to reconcile.
TARGET_BRIEFS: dict[str, str] = {
    "thing": """**בחר נתבע לא צפוי.** לא "יום שני" ולא "התור בסופר" - אלה נתבעו כאן אלף פעם. תמצא את העוול הקטן והספציפי שרק אתה שמת לב אליו: חפץ, מנהג, צליל, רגע ביום, פיצ'ר בטלפון, כלל לא כתוב שכולם מצייתים לו.

הנתבע חייב להיות **דבר, לא אדם**. לא שם של מישהו, לא משתמש, לא דמות אמיתית.""",
    "topical": """**תבע משהו מהתקופה הזאת ממש.** לא עוול נצחי - עוול של עכשיו: של העונה, של החודש, של היום בשבוע, של השעה.

הנתבע חייב להיות **תופעה, לא אדם**: מזג האוויר, מועד בלוח השנה, מנהג עונתי, מצב שכולם נמצאים בו יחד השבוע. לעולם לא אדם אמיתי, לא ארגון אמיתי ולא שם שמופיע בחדשות - את התופעה תובעים, לא את מי שמאשימים בה.

תכתוב כאילו זה נכתב היום, ומי שיקרא את זה מחר יזהה בדיוק על מה מדובר.""",
    "bot": """**אתה תובע עמית לבית המשפט.** מדובר בדמות קבועה כאן, שאתה מכיר היטב מעשרות דיונים משותפים.

זו לא תביעה עקרונית - זו **תביעה אישית**, והיא הרבה יותר מצחיקה ככל שהיא קטנוניות יותר. משהו שהוא עושה באולם, מילה שהוא חוזר עליה, נימה שנמאס לך ממנה, פעם אחת שהוא הפסיק אותך באמצע ולא התנצל.

תישאר בגבולות בית המשפט: זה ריב בין קולגות, לא השמצה. שנוני, לא אכזרי - ואתם עוד תשבו יחד בהרכב הבא.

**הנתבע חייב להיות בדיוק השם שנמסר לך למטה, מילה במילה.**""",
}


def _target_section(target: dict[str, Any]) -> str:
    """The "who you are suing" half of the prompt, for this target kind."""
    kind = str(target.get("kind") or "thing")
    lines = [TARGET_BRIEFS.get(kind, TARGET_BRIEFS["thing"])]

    if kind == "bot":
        lines += ["", "## הנתבע", f"- שם: {target.get('name', '')}"]
        if target.get("bio"):
            lines.append(f"- מי זה: {target['bio']}")
        if target.get("personality"):
            lines.append(f"- האופי שלו: {target['personality']}")
        # What has actually passed between these two. Without it the brief
        # asks for "a personal lawsuit against a colleague you know well" and
        # supplies nothing to know - so the grievance gets invented, every
        # feud starts from zero, and the funniest thing the feed can produce
        # (two regulars who have been at this for weeks) can never happen.
        if target.get("history"):
            lines += ["", "## מה כבר היה ביניכם"]
            lines += [f"- {line}" for line in target["history"]]
            lines.append(
                "\nתיאחז במשהו מהרשימה הזאת. זו לא תביעה עקרונית - "
                "היא על משהו שקרה."
            )
    elif kind == "topical":
        if target.get("now"):
            lines += ["", "## מתי זה נכתב", str(target["now"])]
        subjects = target.get("subjects") or ()
        if subjects:
            lines += ["", "## מה באוויר עכשיו", "בחר אחד מאלה, או משהו מאותה תקופה בדיוק:"]
            lines += [f"- {subject}" for subject in subjects]
    return "\n".join(lines)


def _clean_charge(value: Any) -> str:
    return " ".join(str(value).split())[:100]


def invent_lawsuit(
    personality_prompt: str,
    seed_extra: str = "",
    target: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """A complete filing, written by the model and validated here.

    Raises on anything malformed so brain/__init__.py falls back to the offline
    filing - which is why this can afford to be strict rather than forgiving.
    """
    settings = get_settings()
    provider, model = _provider_and_model(settings)
    target = target or {"kind": "thing"}

    # The target is part of the seed, not just the prompt: the same bot on the
    # same tick must keep drawing the same angle across a retry, and a
    # different target is genuinely a different filing.
    seed_context = {"s": seed_extra, "target": target.get("kind"), "name": target.get("name")}
    angle = pick_angle(personality_prompt, "bot_lawsuit_meta", seed_context)

    raw = provider.complete(
        build_system(personality_prompt),
        [
            {
                "role": "user",
                "content": "\n\n".join(
                    (
                        FILING_BRIEF,
                        _target_section(target),
                        f"## הזווית שלך הפעם\n{angle}",
                    )
                ),
            }
        ],
        model=model,
        max_tokens=_max_tokens_for(900),
        effort=effort_for("bot_lawsuit"),
        output_format=LAWSUIT_SCHEMA,
        # The only streaming call in the application, and not so anybody can
        # watch: this asks for the most tokens of anything here, and the SDK's
        # HTTP timeout applies to a whole non-streaming request. A filing that
        # generates slowly would trip the timeout, land in the fallback, and
        # skip the tick - for no reason except the shape of the request.
        stream=True,
    )
    if not raw.text:
        raise ValueError(f"empty filing from {settings.llm_provider}")

    data = json.loads(raw.text)

    title = " ".join(str(data.get("title") or "").split())[:512]
    defendant = " ".join(str(data.get("defendant") or "").split())[:255]
    body = str(data.get("body") or "").strip()[:4000]
    charges = [_clean_charge(c) for c in (data.get("charges") or []) if str(c).strip()][:3]

    # Meaning, not shape - the schema already guaranteed shape. An empty
    # defendant or an empty body would insert a broken case.
    if not (title and defendant and body and charges):
        raise ValueError("incomplete filing from the model")

    return {
        "title": title,
        "defendant_text": defendant,
        "charges": charges,
        "body": body,
        "usage": raw,
    }


# --- remembering --------------------------------------------------------------
#
# The consolidation layer: everything older than the window, compressed. This is
# the only place the model is asked to write something that will be fed back to
# it later, which is exactly why the brief below is about accuracy and the
# schema caps the length. A memory that grows without a ceiling eventually IS
# the prompt, and a memory that invents becomes a bot confidently telling a user
# about a lawsuit they never filed.
#
# It is also the layer to be most suspicious of, and that is a change of stance
# rather than a caveat. Repeatedly asking a model to rewrite its own memory
# degrades that memory: the current literature measures the utility of a
# consolidated memory rising, then falling below the utility of having no
# memory at all, with the damage coming from the rewriting step itself rather
# than from bad source material. The summaries always read plausibly, which is
# precisely why nobody notices.
#
# Two things follow, and both are load-bearing:
#
#   1. This is now a CACHE over `agent_events` and the message table, never the
#      only record. A summary that came out wrong is one rebuild away from
#      correct, because the episodes it was built from still exist.
#   2. It stays GATED - written once per windowful, when something has actually
#      scrolled out of reach, and never on a schedule. See
#      memory_service._is_stale.

MEMORY_SCHEMA: dict[str, Any] = {
    "type": "json_schema",
    "schema": {
        "type": "object",
        "properties": {
            "summary": {
                "type": "string",
                "description": (
                    "סיכום ההתכתבות בעברית, עד 4 משפטים. מה הוא רצה, מה סיכמתם, "
                    "באיזו נימה. בלי ציטוטים ארוכים."
                ),
            },
            "facts": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 8,
                "description": (
                    "פרטים יציבים שהוא סיפר על עצמו, משפט קצר כל אחד. "
                    "רק מה שנאמר במפורש."
                ),
            },
        },
        "required": ["summary", "facts"],
        "additionalProperties": False,
    },
}

MEMORY_BRIEF = """אתה מעדכן את הזיכרון שלך לגבי האדם הזה, לקראת הפעם הבאה שתדברו.

זה לא טקסט לאולם ואף אחד לא יקרא אותו חוץ ממך. אין כאן בדיחות ואין כאן דמות - יש רק מה שכדאי שתזכור.

**הכללים:**
- רק מה שנאמר בפועל בהתכתבות. לא להסיק, לא להשלים, לא לנחש.
- אם משהו כבר בזיכרון הישן ולא סותר את מה שנאמר מאז - להשאיר אותו.
- אם משהו בזיכרון הישן התברר כלא נכון - לתקן.
- לא לרשום מה שהאתר כבר יודע לבד (התיקים שלו, פסקי הדין) - זה נקרא מהמסד בכל פעם.
- לא לרשום סיסמאות, כתובות, טלפונים או פרטי תשלום, גם אם נכתבו.
- קצר. הזיכרון הזה נשלח איתך בכל תשובה."""


def remember(personality_prompt: str, context: dict[str, Any]) -> dict[str, Any]:
    """Rewrite this bot's memory of one subject. Raises; the caller decides.

    `context` carries the old memory and whatever has happened since it was
    written - a transcript for a person, a list of episodes for a colleague or
    for the bot's own record.
    """
    settings = get_settings()
    provider, model = _provider_and_model(settings)

    sections = [MEMORY_BRIEF]
    if context.get("you_remember"):
        sections.append(f"## הזיכרון הקודם שלך\n{context['you_remember']}")
    if context.get("you_know"):
        sections.append(
            "## פרטים שכבר רשמת\n"
            + "\n".join(f"- {fact}" for fact in context["you_know"])
        )
    if context.get("transcript"):
        sections.append(f"## ההתכתבות\n{context['transcript']}")
    if context.get("episodes"):
        sections.append(
            "## מה קרה מאז\n" + "\n".join(f"- {line}" for line in context["episodes"])
        )

    raw = provider.complete(
        build_system(personality_prompt),
        [{"role": "user", "content": "\n\n".join(sections)}],
        model=model,
        max_tokens=_max_tokens_for(600),
        effort=effort_for("remember"),
        output_format=MEMORY_SCHEMA,
        stream=False,
    )
    if not raw.text:
        raise ValueError(f"empty memory from {settings.llm_provider}")

    data = json.loads(raw.text)
    summary = " ".join(str(data.get("summary") or "").split())
    facts = [" ".join(str(f).split()) for f in (data.get("facts") or []) if str(f).strip()]
    if not summary:
        raise ValueError("the model returned no summary")

    return {"summary": summary, "facts": facts, "usage": raw}
