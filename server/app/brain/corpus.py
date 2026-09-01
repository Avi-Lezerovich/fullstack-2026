"""The offline generator's raw material: the court minute, and the filing lists.

Content, not logic. Nothing here imports anything.

--- what this used to be, and why it is smaller now --------------------------

This file was once a twelve-tone phrase bank, ~800 lines of it, and every
personality drew its lines from the bank matching its `[tone:x]` marker. The
goal was for the credential-free path to be a decent read on its own: a court
of characters that worked with no API key at all.

It was the wrong goal, pursued well. A phrase bank cannot read the case it is
commenting on, so its idea of "in character" is a register - and a register
recombined from a fixed pool is recognisable within about a day of use. The
result was output that *looked* like a personality speaking and was not: the
same nine openings, the same shapes, attached to whatever case happened to be
in front of it. The site did not read as having a cheap fallback. It read as
having shallow characters, which is far worse, and it is precisely what got
this whole layer rebuilt.

So the offline path stopped auditioning. **It is the court stenographer now.**
It writes the minute: what was filed, who was heard, what was decided - flat,
correct, impersonal, and visibly not somebody speaking. Nobody mistakes a
docket entry for a character, which is the entire point. When the model is
unavailable the site says less, in a register that is honest about saying less,
instead of putting words in twenty personalities' mouths.

What that buys, concretely:

  * `docker compose up` with an empty `.env` still runs the whole application,
    end to end, which is a hard requirement and the reason this file exists.
  * The determinism the trial engine leans on is untouched: same inputs, same
    text, so a retried tick reproduces its own comment.
  * Nothing here has to be *good*, so nothing here has to grow. The pressure to
    keep feeding the phrase bank is gone.

**Everything is written in gender-neutral Hebrew**, and it is far easier now
than it was: a minute is impersonal by nature, so the first-person forms that
used to need careful handling ("אני מסיימת" in a male judge's mouth) simply do
not arise. The one remaining rule is the old one - past tense and nominal
forms are safe, present-tense first person is not.

Placeholders like {defendant} and {charge} are filled in a second pass from the
case itself. They are what keep the minute about *this* trial: a docket entry
with no case details in it would be worse than saying nothing.

The `LAWSUIT_*` lists below are the exception and stay large. They feed the
offline filing, which is still a whole invented case, and their size is what
stops a credential-free demo filing the same lawsuit twice in an afternoon.
"""

from __future__ import annotations

# --- the minute, per task ---------------------------------------------------
#
# One small set per task, register-neutral, deliberately clerical. Several
# shapes each, because even a docket entry that repeats itself verbatim reads
# as broken rather than as terse - and because the seed needs something to
# choose between.
#
# `{...}` slots are all CONTEXT slots now: there are no phrase banks left to
# draw from, so every variable part of a line comes from the case. That is the
# structural difference from what was here before, and it is why this cannot
# drift back into impersonating a character.

TEMPLATES: dict[str, list[str]] = {
    "jury_deliberation": [
        "המושבע עיין בכתב התביעה בעניין {defendant} ורשם את עמדתו לפרוטוקול.",
        "נשמעה התייחסות לסעיף {charge}. העמדה נרשמה.",
        "המושבע ביקש לציין כי טענות הצדדים בעניין {defendant} נשקלו במלואן.",
        'עמדת המושבע בתיק "{title_quote}" נרשמה לפרוטוקול.',
        "נרשמה התייחסות לטענת {plaintiff} ולסעיף {charge}.",
        "המושבע שמע את שנאמר עד כה ומיקם את עמדתו בהתאם.",
        "נרשמה הסתייגות בנוגע להיקף הראיות שהוצגו בעניין {defendant}.",
        "המושבע ביקש להפנות את תשומת הלב לסעיף {charge} ולנסיבותיו.",
        "נרשם כי עמדת המושבע גובשה לאחר עיון בטענות {plaintiff}.",
        'המושבע הצטרף לדיון בתיק "{title_quote}" והעמדה תועדה.',
        "נשמעה הערה בנוגע למשקל שיש לתת לסעיף {charge}.",
        "נרשמה עמדה עצמאית, שאינה זהה לזו שנשמעה קודם לכן.",
        "המושבע עיין בחומר, שקל את הטענות, והעמדה נרשמה כלשונה.",
        "נרשמה התייחסות מסויגת בעניין {defendant}, בכפוף לראיות שהוצגו.",
    ],
    "verdict": [
        "בית המשפט שקל את הראיות והכריע: {verdict_word}.",
        "לאחר ספירת קולות המושבעים ({tally}), ניתנת ההכרעה: {verdict_word}.",
        "בעניין {defendant}: {verdict_word}. ההכרעה נרשמה.",
        'ההכרעה בתיק "{title_quote}": {verdict_word}.',
        "על יסוד הטענות שנשמעו ובכללן סעיף {charge}: {verdict_word}.",
    ],
    "sentence": [
        "נגזר: התנצלות בכתב בפני {plaintiff}, בתוך שבעה ימים.",
        "נגזר: איסור מגע עם {defendant} למשך ארבעה עשר יום.",
        "נגזר: רישום הערה בתיק בגין {charge}.",
        "נגזר: הצגת תוכנית תיקון מפורטת בישיבה הבאה.",
        "נגזר: פיצוי סמלי לתובע, בהתאם לסעיף {charge}.",
    ],
    "moderation_note": [
        "התוכן נסרק. הרישום עודכן בהתאם.",
        "נבדק על סמך הלקסיקון. ההחלטה נרשמה.",
        "הבדיקה הושלמה והתיעוד נשמר.",
        "נבדק. אין שינוי בסיווג.",
    ],
    "draft_lawsuit": [
        "מוגשת בזאת תביעה בעניין {defendant}.\n\n"
        "לטענת התובע מתקיים {charge}, באופן החוזר על עצמו ומקשה על ההתנהלות היומיומית.\n\n"
        "מתבקש בית המשפט לדון בעניין ולקבוע סעד מתאים.",
        "כתב תביעה בעניין {defendant}.\n\n"
        "העילה: {charge}. המקרה נמשך לאורך זמן ולא ניתן לו מענה.\n\n"
        "מתבקש בית המשפט לזמן את הצדדים ולהכריע.",
    ],
    "bot_lawsuit": [
        "מוגשת בזאת תביעה נגד {defendant}.\n\n"
        "העילה: {charge}. ההתנהלות נמשכת ואין לה הצדקה.\n\n"
        "מתבקש בית המשפט לדון בעניין ולקבוע סעד.",
        "כתב תביעה: {defendant}.\n\n"
        "לטענת התובע מתקיים {charge}, בנסיבות שאינן מותירות מקום לספק.\n\n"
        "מתבקש סעד מתאים.",
    ],
    "suggest_comment": [
        "הערה לתיק בעניין {defendant}.",
        "התייחסות לסעיף {charge}.",
        'הערה נרשמה בעניין "{title_quote}".',
    ],
    "bot_comment": [
        "התיק בעניין {defendant} נקרא ונרשם.",
        "נרשמה התייחסות לסעיף {charge}.",
        'הערה לתיק "{title_quote}" נרשמה.',
        "העיון בתיק בעניין {defendant} הושלם.",
    ],
    "bot_comment_reply": [
        "ההתייחסות התקבלה ונרשמה.",
        "נרשמה תגובה בעניין {defendant}.",
        "התקבלה הערה נוספת לתיק. הרישום עודכן.",
    ],
    "bot_reply": [
        "ההודעה התקבלה ונרשמה.",
        "התקבלה פנייה. הרישום עודכן.",
        "נרשמה פנייה בעניין {defendant}.",
        "ההתכתבות תועדה.",
    ],
}


# Titles for lawsuits a bot files on its own initiative.
LAWSUIT_TITLES: list[str] = [
    "התביעה נגד {defendant}",
    "בעניין {defendant}",
    "תלונה חמורה בנוגע ל{defendant}",
    "{defendant} - כתב תביעה",
    "הגיע הזמן לדבר על {defendant}",
    "{defendant}: הפעם זה נגמר",
    "בקשה דחופה בעניין {defendant}",
    "מדינת המתוסכלים נגד {defendant}",
    "על {defendant}, ועל מה שהוא עולל",
    "כתב אישום: {defendant}",
    "{defendant} - די",
    "התיק שאיש לא העז לפתוח: {defendant}",
    "עתירה בעניינו של {defendant}",
    "{defendant} ואני. סוף סוף באולם.",
    "מי יעצור את {defendant}?",
    "לכבוד בית המשפט: {defendant}",
]

# Bots only ever sue things, never registered users. That is enforced by
# construction here, and separately by a database check in the worker for
# filings the live model writes.
LAWSUIT_DEFENDANTS: list[str] = [
    "יום שני",
    "התור בסופר",
    "הגשם בדיוק אחרי שטיפת הרכב",
    "הקפה שהתקרר",
    "השכן מלמעלה",
    "הסוללה שנגמרה ב-3%",
    "האוטובוס שהקדים",
    "ההודעה שנשלחה בטעות",
    "המעלית התקועה",
    "הגרביים שנעלמו בכביסה",
    "ההתראה של השעון המעורר",
    "הרמזור שמתחלף רק כשמגיעים אליו",
    "הקפיץ בעט שנעלם",
    "האדם שעומד בצד שמאל של הדרגנוע",
    "הסיסמה שדורשת תו מיוחד",
    "העגלה עם הגלגל העקום",
    "הקול של עצמי בהקלטה",
    "הפלסטיק שעוטף את הפלסטיק",
    "השקית שנקרעה בדיוק ליד הבית",
    "ההודעה 'הקלד/ה...' שנעלמת",
    "הכיסא שחורק רק כשיש שקט",
    "הזמן שבין 'שולח קורות חיים' ל'נחזור אליך'",
    "המטען שעובד רק בזווית מסוימת",
    "האוטובוס שעצר שני מטרים אחרי התחנה",
    "הפקק שנפתח בלי סיבה ובלי הסבר",
    "הכפית האחרונה בצנצנת",
    "ההודעה הקולית בת ארבע הדקות",
    "הדלת שכתוב עליה 'משוך' ואני דחפתי",
    "השיר שנתקע בראש מאז יום שלישי",
    "המדבקה שלא יורדת עד הסוף",
    "התאריך שנשמע רחוק ופתאום הוא מחר",
    "השאלה 'אז מה נשמע?'",
    "הרגע שבו נזכרתי מה רציתי להגיד",
    "המקרר שמזמזם רק בלילה",
    "המים שיוצאים קרים אחרי שכבר נכנסתי",
    "האוזנייה הימנית",
    "השרוך שנפתח בדיוק כשהידיים תפוסות",
    "העדכון שהתקין את עצמו בלילה",
    "החניה שהתפנתה שנייה אחרי שוויתרתי",
    "הקבוצה בוואטסאפ שאי אפשר לצאת ממנה",
    "הכריך שנפל על הצד המרוח",
    "השלט שהסוללות שלו נגמרות רק באמצע",
    "הרעש מהשיפוץ שמתחיל בשבע",
    "המילה שנמצאת על קצה הלשון",
    "הקבלה שדהתה בדיוק לפני שנזכרתי בה",
    "היום שלישי שמתחזה ליום חמישי",
]

LAWSUIT_CHARGES: list[str] = [
    "גרימת עייפות",
    "הפרת שלווה",
    "בזבוז זמן יקר",
    "עוגמת נפש",
    "רשלנות חמורה",
    "הטרדה רגשית",
    "גניבת דעת",
    "הפרת אמון",
    "התעללות בציפיות",
    "הפרת חוזה בלתי כתוב",
    "זלזול בוטה בזמן הזולת",
    "יצירת תקווה שווא",
    "הסבת נזק למצב הרוח",
    "התנהגות בלתי הולמת חפץ",
    "אי מתן התראה סבירה",
    "הכשלה בכוונת מכוון",
    "פגיעה בשגרת הבוקר",
    "התחמקות שיטתית",
    "עיכוב בלתי מוסבר",
    "גרימת בושה ברבים",
    "הפרעה למנוחת הנפש",
    "הצגת מצג שווא",
    "חוסר תום לב בסיסי",
    "פגיעה בכבוד התור",
    "התעלמות מכללי ההיגיון",
    "העמסת מטלות מיותרות",
]

# Every slot a template may use. There is no second category any more: with
# the tone banks gone, an unresolved slot is a typo rather than a missing
# bank, and the test that walks TEMPLATES against this tuple is what catches
# it before a juror renders "{stnace}" into the permanent record.
CONTEXT_SLOTS = ("defendant", "charge", "title_quote", "tally", "plaintiff", "verdict_word")
