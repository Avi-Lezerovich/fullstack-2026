"""What is going on *right now*, for bots that want to sue something topical.

Pure and dependency-free: a datetime in, a few Hebrew strings out. No network,
no feed, no API key - which is deliberate. The worker must never gain a failure
mode that lives outside this machine, and "the trial engine stalled because a
news API rate-limited us" is exactly that.

**Why the clock and not the headlines.** Two reasons, and the second is the
real one:

* Neither end of the system can actually know today's news. The worker has no
  feed, and a language model's knowledge has a cutoff - asking it for "current
  events" gets you confident, stale, invented ones.
* A bot filing a satirical lawsuit against a *named real person or company* is
  harassment with a court date attached, which is the same rule that already
  stops bots suing registered users. So the topical defendant is always the
  **phenomenon**, never the person: גל החום, not whoever is being blamed for it.

What is left after those two constraints is still a lot: Israel in late August
is a specific, funny, shared experience, and so is the first rain, the switch
to winter time, and the week the school year starts. That is what this module
supplies.

For genuinely current subjects, `TOPICAL_SUBJECTS` lets an operator paste in
whatever is in the air this week without a deploy - a human stays in the loop
on what the bots are allowed to riff on.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

log = logging.getLogger(__name__)

# Everything here is about *local* experience - "the 8am traffic", "Friday
# afternoon when everything shuts" - so it has to run on Israel time, not the
# UTC the database stores. Three hours of drift would put the evening bucket
# on the afternoon and, near midnight, the whole weekday one day out.
COURT_TZ = "Asia/Jerusalem"

# DST-less fallback, used only if the zone database is unavailable. Wrong by an
# hour for part of the year, which is a far better failure than a worker that
# cannot file a lawsuit.
_FALLBACK_OFFSET = timedelta(hours=2)


def local_now(utc_now: datetime) -> datetime:
    """A naive UTC datetime, converted to the court's local wall clock.

    `zoneinfo` is stdlib, but the IANA database is NOT present on a slim Debian
    image unless something provides it - hence `tzdata` in requirements.txt.
    The fallback exists so that a missing tz database degrades to "an hour off
    in winter" rather than taking the worker down.
    """
    try:
        from zoneinfo import ZoneInfo

        return utc_now.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(COURT_TZ)).replace(
            tzinfo=None
        )
    except Exception:  # pragma: no cover - only without tzdata installed
        log.warning("no tz database for %s; using a fixed offset", COURT_TZ, exc_info=True)
        return utc_now + _FALLBACK_OFFSET


# Israel by Gregorian month. The Hebrew calendar drifts against this by a few
# weeks a year, so the festival entries are written loosely ("עונת החגים")
# rather than pinned to a date a lunisolar calendar would move.
BY_MONTH: dict[int, tuple[str, ...]] = {
    1: (
        "אמצע החורף",
        "הגשם שלא מפסיק",
        "החשבון של חברת החשמל אחרי חודש של תנור",
        "עונת השפעת במשרד",
    ),
    2: (
        "סוף החורף שלא נגמר",
        "ט\"ו בשבט והשקדייה שכבר פרחה בינואר",
        "היום הכי אפור בשנה",
        "המעיל שכבר נמאס ממנו",
    ),
    3: (
        "ניקיונות פסח שמתחילים מוקדם מדי",
        "המעבר לשעון קיץ וגניבת השעה",
        "פורים והתחפושת של הרגע האחרון",
        "האביב שמבלבל את האף",
    ),
    4: (
        "פסח והכלים שצריך להחליף",
        "השבוע שבו אף אחד לא עובד באמת",
        "החמסין הראשון של השנה",
        "החופש שנגמר ביום ראשון",
    ),
    5: (
        "העשן של ל\"ג בעומר",
        "המזגן שמופעל בפעם הראשונה ומריח מוזר",
        "שבועות והגבינות שנגמרו במכולת",
        "החום שהגיע בלי להודיע",
    ),
    6: (
        "תקופת המבחנים",
        "סוף שנת הלימודים והמסיבות",
        "הלחות שחוזרת",
        "החשבון על המזגן שרץ מאז מאי",
    ),
    7: (
        "החופש הגדול ביום השלישי שלו",
        "שיא הקיץ",
        "הלחות שהופכת כל יציאה לרעיון רע",
        "המקומות בחוף שנתפסו ב-6 בבוקר",
    ),
    8: (
        "גל החום של אוגוסט",
        "החופש הגדול שלא נגמר",
        "הקניות לבית הספר",
        "אוגוסט. פשוט אוגוסט.",
        "החשבון על החשמל אחרי חודש של מזגן",
    ),
    9: (
        "היום הראשון של שנת הלימודים",
        "עונת החגים והפקקים שלה",
        "ראש השנה והארוחה שנמשכת שש שעות",
        "החזרה לשגרה שכולם מדברים עליה",
    ),
    10: (
        "אחרי החגים, שמעולם לא מגיע",
        "המעבר לשעון חורף והחושך ב-17:00",
        "סוכות והסוכה שקורסת ברוח",
        "הבלגן שנשאר מהחגים",
    ),
    11: (
        "הגשם הראשון והפקק שהוא מביא",
        "החושך שמגיע אחרי הצהריים",
        "המעיל שלא מצאתי בארון",
        "הרגע שבו מגלים שהתריס לא נסגר",
    ),
    12: (
        "הקור שנכנס לבית ולא יוצא",
        "חנוכה והסופגניות שכבר מוצגות מאוקטובר",
        "סוף השנה האזרחית וסיכומיה",
        "החשבון השנתי שכולם שולחים בדצמבר",
    ),
}

BY_WEEKDAY: dict[int, tuple[str, ...]] = {
    # Monday=0 in Python; the Israeli work week starts Sunday.
    6: ("יום ראשון, תחילת שבוע העבודה", "הבוקר שאחרי סוף השבוע"),
    0: ("יום שני, שכבר נתבע כאן פעמים רבות", "אמצע השבוע שמתחיל מוקדם מדי"),
    1: ("יום שלישי, היום חסר התכונות", "האמצע המדויק של השבוע"),
    2: ("יום רביעי, שכבר מריח סוף שבוע ועוד לא", "היום שבו נגמר הכוח"),
    3: ("יום חמישי והפקקים שלו", "הערב שבו כולם יוצאים בבת אחת"),
    4: ("יום שישי הקצר מדי", "הקניות של שישי בצהריים", "השעה שבה נסגר הכול"),
    5: ("שבת והשקט שהשכנים לא שמעו עליו", "המנוחה שלא הספיקה"),
}

BY_HOUR: tuple[tuple[range, tuple[str, ...]], ...] = (
    (range(0, 6), ("השעה שבה אי אפשר להירדם", "הרעש שנשמע רק בשלוש לפנות בוקר")),
    (range(6, 10), ("הבוקר המוקדם מדי", "הפקק של שמונה בבוקר", "הקפה הראשון שלא הספיק")),
    (range(10, 14), ("הרעב של אחת עשרה וחצי", "הפגישה שנקבעה לצהריים")),
    (range(14, 18), ("הצניחה של ארבע אחר הצהריים", "השעה שבה נגמרת הסבלנות")),
    (range(18, 22), ("הערב שנגמר לפני שהתחיל", "הפקק של החזרה הביתה")),
    (range(22, 24), ("הלילה שנגנב במסך", "הרגע שבו כבר מאוחר מדי להתחיל משהו")),
)


def _hour_bucket(hour: int) -> tuple[str, ...]:
    for span, subjects in BY_HOUR:
        if hour in span:
            return subjects
    return ()


def current_subjects(now: datetime, extra: tuple[str, ...] = ()) -> list[str]:
    """Everything topical about this moment, most specific first.

    `extra` is the operator's own list (TOPICAL_SUBJECTS) and leads, because a
    human chose it deliberately and it is the only genuinely current input the
    system has.
    """
    return [
        *extra,
        *BY_MONTH.get(now.month, ()),
        *BY_WEEKDAY.get(now.weekday(), ()),
        *_hour_bucket(now.hour),
    ]


def describe(now: datetime, extra: tuple[str, ...] = ()) -> str:
    """A one-line "here is when you are" for the model's prompt."""
    weekday = ("שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת", "ראשון")[now.weekday()]
    line = f"יום {weekday}, {now.day} ב{_MONTH_NAMES[now.month]}, השעה {now.hour:02d}:00"
    if extra:
        line += f". מה שבאוויר כרגע: {', '.join(extra)}"
    return line


_MONTH_NAMES = {
    1: "ינואר",
    2: "פברואר",
    3: "מרץ",
    4: "אפריל",
    5: "מאי",
    6: "יוני",
    7: "יולי",
    8: "אוגוסט",
    9: "ספטמבר",
    10: "אוקטובר",
    11: "נובמבר",
    12: "דצמבר",
}
