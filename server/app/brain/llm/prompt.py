"""On getting interesting text out of it -------------------------------------

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

import random
from typing import Any

from ...config import get_settings
from .. import offline


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
    # The one brief that spends most of its words undoing STYLE_RULES.
    #
    # Block 1 of the system prompt tells every call on this site to be
    # specific, to surprise, to fasten onto an absurd detail and to sound like
    # somebody in particular. That block is byte-identical for all 31
    # personalities and all ten tasks, which is the entire shared cache prefix
    # this application has - so a proofreading task cannot be given a system
    # prompt of its own without paying for it on every other call. It has to
    # countermand it here instead, in the user turn, which is also the last
    # thing read before the answer.
    #
    # Hence the flat prohibitions. "Correct the text" alone produced a
    # perfectly good filing that the user had not written.
    "correct_text": (
        "מישהו כתב טקסט בעצמו ומבקש שתגיה אותו. אתה מגיה, לא כותב.\n\n"
        "**מה לתקן:** שגיאות כתיב, דקדוק, התאמת מין ומספר, מילות יחס, "
        "פיסוק ורווחים כפולים. בלי ניקוד.\n\n"
        "**מה אסור לגעת בו:** המשמעות, הסגנון, סדר המשפטים, אורך הטקסט, "
        "וכל מילה שאין בה שגיאה. לא לשפר ניסוח, לא להוסיף מילה שלא הייתה שם, "
        "לא למחוק משפט, לא להוסיף לשון משפטית, ולא להסביר מה תיקנת. אם הטקסט "
        "תקין - תחזיר אותו בדיוק כמו שהוא.\n\n"
        "**הכללים על אופי, קול והפתעה לא חלים כאן.** זה לא הטקסט שלך והקול "
        "בו אינו שלך. לשמור על מבנה הפסקאות ועל השורות הריקות כפי שהם.\n\n"
        "יש להחזיר אך ורק את הטקסט המתוקן, בלי מרכאות ובלי הקדמה."
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

# And one task gets no angle whatsoever. Every line in MOVES and HOOKS is an
# instruction to be interesting - fasten onto the absurd detail, land the last
# sentence - which is exactly the wrong thing to hand somebody proofreading a
# stranger's sentences. An angle on a correction is an invitation to rewrite.
_NO_ANGLE = {"correct_text"}


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
    if task in _NO_ANGLE:
        return ""
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

    # The one field that cannot be a bullet.
    #
    # Everything above is a fact about a case - one short line each, and the
    # "- label: value" shape is what keeps them scannable. This is a whole
    # document that has to come back out the other side unchanged, and a
    # three-paragraph filing rendered as "- הטקסט: ..." gives the model no way
    # to see where the user's text stops and the instructions resume. Fenced,
    # and last, so the closing fence is the final thing read before it answers.
    user_text = context.get("user_text")
    if user_text:
        lines += ["", "## הטקסט שנמסר", "<<<", str(user_text), ">>>"]

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
