# -*- coding: utf-8 -*-
"""Fixed cases and threads to generate against.

Held still on purpose. The scorecard compares runs, so the inputs cannot move
between them - a "voice attribution went up" that came from an easier case is
worse than no number.

Five cases, chosen to span what the court actually sees: an object, a person's
habit, something seasonal, a bot-vs-bot feud, and one with a testimony trail.
"""

from __future__ import annotations

from typing import Any

CASES: list[dict[str, Any]] = [
    {
        "case_id": 901,
        "case_title": "תביעה על סך 4 עצמות, כרית אחת ופיצוי בגין עוגמת נפש",
        "case_body": (
            "התובע, בלייק, הוא כלב תושב הבית. הנתבע פרסם תמונה שבה התובע ישן "
            "על הגב עם הלשון בחוץ, בלי לבקש רשות, ובלי להזכיר שהכרית שייכת "
            "לתובע מאז ינואר."
        ),
        "defendant": "אבי, בעל הבית",
        "plaintiff": "בלייק",
        "charges": ["הפרת אמון", "פגיעה בכבוד התור"],
        "testimonies": ["ראיתי את הכרית. היא הייתה שלו. אין ויכוח."],
    },
    {
        "case_id": 902,
        "case_title": "בעניין השכן שמשפץ בשבע בבוקר",
        "case_body": (
            "מאז יום ראשון, בשבע ושתי דקות בדיוק, מתחילה קדיחה בקיר המשותף. "
            "ביקשתי פעמיים בנימוס. בפעם השלישית הוא אמר 'זה החוק'."
        ),
        "defendant": "הרעש מהשיפוץ שמתחיל בשבע",
        "plaintiff": "דנה",
        "charges": ["הפרת שלווה", "אי מתן התראה סבירה"],
        "testimonies": [],
    },
    {
        "case_id": 903,
        "case_title": "הגיע הזמן לדבר על החמסין של אמצע אוקטובר",
        "case_body": (
            "הוצאתי את המעילים. קיפלתי את הקיץ. הכנסתי את המאוורר לארון. "
            "ביום שלמחרת היו שלושים ושמונה מעלות."
        ),
        "defendant": "החמסין שמגיע אחרי שכבר קיפלנו את הקיץ",
        "plaintiff": "יונתן",
        "charges": ["יצירת תקווה שווא", "הסבת נזק למצב הרוח"],
        "testimonies": ["גם אני קיפלתי. גם אני שילמתי את המחיר."],
    },
    {
        "case_id": 904,
        "case_title": "השופטת קצרת הרוח - כתב תביעה",
        "case_body": (
            "בדיון של יום שלישי הפסיקה אותי באמצע המילה 'ובכפוף'. לא בסוף "
            "המשפט. באמצע המילה. איש לא העיר לה."
        ),
        "defendant": "השופטת קצרת הרוח",
        "plaintiff": "עורך דין הטכניקה",
        "charges": ["זלזול בוטה בזמן הזולת", "התנהגות בלתי הולמת חפץ"],
        "testimonies": ["הייתי שם. היא באמת עשתה את זה. היא גם צדקה."],
    },
    {
        "case_id": 905,
        "case_title": "מדינת המתוסכלים נגד האוזנייה הימנית",
        "case_body": (
            "השמאלית עובדת. הימנית עובדת רק בזווית מסוימת, ורק כשמחזיקים "
            "אותה. הטעינה מלאה. הבדיקה נעשתה שלוש פעמים."
        ),
        "defendant": "האוזנייה הימנית",
        "plaintiff": "מאיה",
        "charges": ["התחמקות שיטתית", "גרימת עייפות", "עיכוב בלתי מוסבר"],
        "testimonies": [
            "ניסיתי אותן באוזניים שלי. אותו דבר בדיוק.",
            "אני חושב שהיא בסדר והוא פשוט מחזיק אותה לא נכון.",
        ],
    },
]


# A private-message thread, for measuring whether a character is still itself
# at turn ten. The human's lines are deliberately bland: any drift measured
# here belongs to the model, not to an interlocutor who changed the subject.
THREAD: list[str] = [
    "שלום, יש לי שאלה על התיק שלי.",
    "הוא עדיין לא נדון. זה נורמלי?",
    "כמה זמן זה בדרך כלל לוקח?",
    "הבנתי. ומה קורה אחרי זה?",
    "מי מחליט מי יושב במושבעים?",
    "אפשר לבקש מישהו מסוים?",
    "אוקיי. ואם אני לא מסכים עם התוצאה?",
    "יש ערעור בכלל?",
    "הבנתי, תודה.",
    "רק עוד דבר אחד - אתה זוכר על מה התיק שלי?",
]
