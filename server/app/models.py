"""Database access layer — raw sqlite3 (no ORM).

Owns the connection helper, schema/seed bootstrap, and the absolute paths to the
SQLite file and the schema. Seed fixtures are ported from the old client mock so
the app shows identical content.
"""
import os
import sqlite3
import datetime
from pathlib import Path

from .utils import hash_password

BASE_DIR = Path(__file__).resolve().parents[2]          # repo root
DATABASE_DIR = BASE_DIR / "database"
SCHEMA_PATH = DATABASE_DIR / "init.sql"
DB_PATH = os.environ.get("DATABASE_PATH", str(DATABASE_DIR / "lolsuit.db"))
# Uploaded images live next to the server package (override for Docker volumes).
UPLOAD_DIR = os.environ.get("UPLOAD_DIR", str(BASE_DIR / "server" / "uploads"))


def get_db() -> sqlite3.Connection:
    """Open a connection with dict-like rows and FK enforcement on."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """Create the schema (idempotent) and seed once, if the DB is empty."""
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = get_db()
    try:
        with open(SCHEMA_PATH, "r", encoding="utf-8") as fh:
            conn.executescript(fh.read())
        empty = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"] == 0
        if empty:
            _seed(conn)
    finally:
        conn.close()


# ----------------------------------------------------------------- seed helpers

def _iso(dt: datetime.datetime) -> str:
    """Format as ISO-8601 with millisecond precision and a Z suffix (matches JS)."""
    dt = dt.astimezone(datetime.timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def _hours_ago(hours: float) -> str:
    return _iso(datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours))


# (name, email, days_ago, bio) — ids are assigned in order 1..12.
SEED_USERS = [
    ("דנה כהן", "dana@example.com", 30, "תובעת סדרתית בענייני ספה וכלבים. צדק או כלום."),
    ("יואב לוי", "yoav@example.com", 29, "מתמחה בעוולות חברתיות וביטולים ברגע האחרון."),
    ("מאיה שטרן", "maya@example.com", 28, "אם תנגן Wonderwall בחצות — נתראה באולם."),
    ("איתי אברמוב", "itay@example.com", 27, "חולצות לבנות, קפה חום, ועצבים קצרים."),
    ("רוני גולן", "roni@example.com", 26, "נהגת זהירה, סבלנית כלפי כולם חוץ מצמתים."),
    ("נועה פרידמן", "noa@example.com", 25, "מאמינה שכל מנה מגיעה בזמן. תמיד."),
    ("אלון ברק", "alon@example.com", 24, "אספן הערות TODO ומורשת קוד נטוש."),
    ("מיכל שלו", "michal@example.com", 23, "אכיפה קפדנית של גבולות במשק בית משותף."),
    ("תומר אזולאי", "tomer@example.com", 22, "כל 'עוד אחד אחרון' נרשם ונספר."),
    ("עדי בלום", "adi@example.com", 21, "מתעדת מטענים נעלמים מאז 2019."),
    ("גיא מזרחי", "guy@example.com", 20, "מומחה לתורים, קופות סגורות והפסקות חשודות."),
    ("ליהי שדה", "lihi@example.com", 19, "עוקבת אחרי עוקבים. בעיקר אקסים."),
]

# (follower_idx, followee_idx) pairs — 1-based to match the assigned ids above.
# Gives the "following" feed real content out of the box.
SEED_FOLLOWS = [
    (1, 2), (1, 3), (1, 5),
    (2, 1), (2, 4),
    (3, 1), (3, 2), (3, 6),
    (4, 1), (4, 5),
    (5, 2), (5, 7),
    (6, 1), (6, 3),
    (7, 1),
]

SEED_POSTS = [
    {
        "title": "הכלב שסירב לזוז מהספה",
        "body": "הוריתי בנימוס לנתבע לפנות את הספה. הוא הביט בי, נאנח, וסירב להזיז גף אחד. נאלצתי לישון בכורסה הקטנה כמו פליט בביתי שלי. ניסיתי לפתות אותו בחטיף יוקרתי, אך הוא לקח את החטיף, התמתח לכל אורך הספה, והביט בי במבט של מי שיודע שהחוק לצידו. בית המשפט הנכבד מתבקש להכריע, אחת ולתמיד, מי בעל הבית בסלון הזה — האדם ששילם על הספה, או הכלב שישן עליה.",
        "defendant": "קוקי הגולדן",
        "charges": ["רשלנות פלילית", "עיכוב כרוני"],
        "author_id": 1,
        "hours": 2,
    },
    {
        "title": "החבר שביטל יום לפני הטיול",
        "body": "הזמנו צימר. שילמנו מקדמה. תכננתי ארבעה חודשים. יום לפני הוא כתב שהוא נשאר בבית. תובע פיצוי על נזק נפשי, אובדן חופשה ועלבון אישי. הסיבה שמסר הייתה 'לא בא לי בסוף', כאילו מדובר בהזמנת פיצה ולא בטיול שתוכנן בקפידה במשך חודשים. כבר קניתי כובע מצחיה תואם וערכתי פלייליסט. בית המשפט מתבקש לקבוע שביטול ברגע האחרון הוא לא זכות, אלא עוולה חברתית לכל דבר ועניין.",
        "defendant": "דניאל מ.",
        "charges": ["בגידה חברתית", "הפרת שלוות נפש", "מניפולציה רגשית"],
        "author_id": 2,
        "hours": 5,
    },
    {
        "title": "השכן שמנגן גיטרה בחצות",
        "body": "בכל לילה ב-23:58 הוא מנגן את אותם ארבעה אקורדים של Wonderwall. לא מסיים את השיר. רק האינטרו. אני שומע אותו גם בחלומות. ניסיתי לדפוק בקיר, לשלוח פתק מנומס מתחת לדלת, ואפילו להשמיע בחזרה שיר אחר בעוצמה — אך שום דבר לא עוצר אותו. נדמה שהוא מאמין שיום אחד, אם רק ינגן את האינטרו מספיק פעמים, השיר סוף סוף יסתיים מעצמו. בית המשפט מתבקש להגן על שלוות הלילה של כל הבניין.",
        "defendant": "השכן מקומה 3",
        "charges": ["הפרת שלוות נפש", "ייאוש מכוון"],
        "author_id": 3,
        "hours": 24,
    },
    {
        "title": "הברמן ששפך עליי קפה ולא התנצל",
        "body": "הזמנתי קפוצ'ינו. הברמן החליק, שפך חצי עליי, אמר 'טוב נו' וחזר לבר. החולצה הלבנה החדשה שלי הפכה למפת גלקסיה חומה. לא התנצלות, לא מגבת, לא הצעה לנקות — רק 'טוב נו' שנאמר בנימה של מי שעושה לי טובה. ישבתי שם רטוב, מבוייש ומריח כמו בית קפה שלם, בעוד הוא ממשיך להקציף חלב כאילו דבר לא קרה. בית המשפט מתבקש לקבוע ש'טוב נו' אינו פיצוי מספק על חולצה הרוסה.",
        "defendant": "הברמן עם הקוקו",
        "charges": ["רשלנות פלילית", "מניפולציה רגשית"],
        "author_id": 4,
        "hours": 27,
    },
    {
        "title": "האחות הקטנה שגנבה את הטעינה",
        "body": "המטען נשאר בחדרי לבטח, מחובר לשקע. בשובי מהמקלחת הוא נעלם. הנתבעת שיחקה ב-Roblox כאילו לא קרה דבר. כששאלתי, היא ענתה 'איזה מטען?' בעיניים תמימות מדי בשביל ילדה שמחזיקה את הכבל שלי ביד. זו הפעם השלישית החודש, ולמותר לציין שהמטען שלה שלה נמצא בדיוק שם, על השולחן, טעון במלואו. בית המשפט מתבקש לקבוע גבולות ברורים בנושא בעלות על אביזרי טעינה במשק בית משותף.",
        "defendant": "נועה (אחותי)",
        "charges": ["בגידה חברתית", "רשלנות פלילית"],
        "author_id": 1,
        "hours": 48,
    },
    {
        "title": "הנהג שעצר באמצע הצומת",
        "body": "אור ירוק. הוא עצר. באמצע הצומת. מאחוריו משטרה ו-30 רכבים. בעיני זו הייתה הפעם הראשונה שפגשתי עיכוב כרוני אמיתי. הוא לא בדק טלפון ולא התבלבל — הוא פשוט החליט, ברגע הכי לא מתאים, שזה הזמן לעצור ולחשוב על החיים. הצופר שלי, הצופר של המשטרה, וצופרים של עוד שלושים רכבים לא הזיזו לו. בית המשפט מתבקש לבחון האם יש דבר כזה 'זכות לעצור באמצע צומת' — ואם לא, לקבוע זאת בתקדים מחייב.",
        "defendant": "הסובארו הכחולה",
        "charges": ["עיכוב כרוני", "רשלנות פלילית"],
        "author_id": 5,
        "hours": 72,
    },
    {
        "title": "המסעדה שאיבדה את ההזמנה שלי",
        "body": "הזמנתי דרך אפליקציה. שילמתי. חיכיתי שעה. 'אופס, לא ראינו את ההזמנה'. הציעו לי 10% הנחה על הזמנה הבאה. שאני לא אזמין מהם שוב.",
        "defendant": "המסעדה האסיאתית בקניון",
        "charges": ["רשלנות פלילית", "בגידה חברתית", "ייאוש מכוון"],
        "author_id": 2,
        "hours": 96,
    },
    {
        "title": "האקס שעוקב אחרי בכל פלטפורמה",
        "body": "נפרד ממני לפני שנתיים. עוקב אחריי באינסטה, בלינקדאין, בטיקטוק ובפינטרסט. רואה כל story תוך ארבע דקות. אני יודעת שהוא קורא את זה.",
        "defendant": "האקס",
        "charges": ["הפרת שלוות נפש", "מניפולציה רגשית"],
        "author_id": 3,
        "hours": 120,
    },
    {
        "title": "האב שצופה בטלפון בארוחה משפחתית",
        "body": "יום שישי. כל המשפחה. אבא מסתכל בטלפון כל 30 שניות. כשהוא אומר 'סיימתי' הוא כבר חוזר לגלול. אחר כך הוא נואם על 'הדור הזה'.",
        "defendant": "אבא",
        "charges": ["בגידה חברתית", "מניפולציה רגשית"],
        "author_id": 4,
        "hours": 144,
    },
    {
        "title": "הקופאית בסופר שלא רצתה לפתוח עוד קופה",
        "body": "תור של 12 אנשים. ביקשתי שיפתחו עוד קופה. 'זה לא התפקיד שלי' אמרה. 'אני בהפסקה' השיבה, תוך כדי שהיא אוכלת קרם בוה על חשבון העמדה.",
        "defendant": "הקופאית עם הציפורניים",
        "charges": ["רשלנות פלילית", "עיכוב כרוני"],
        "author_id": 5,
        "hours": 168,
    },
    {
        "title": "המאמן בכושר שצועק 'עוד אחד' 17 פעמים",
        "body": "הוא אמר 'עוד אחד אחרון'. עשיתי. הוא אמר שוב. ושוב. ושוב. עד שלא יכולתי להרים את הזרוע לסבון אחר כך. הזרוע שלי עדיין רועדת.",
        "defendant": "יוסי המאמן",
        "charges": ["מניפולציה רגשית", "ייאוש מכוון", "רשלנות פלילית"],
        "author_id": 6,
        "hours": 192,
    },
    {
        "title": "המתכנת שכתב TODO ועזב את החברה",
        "body": "במערכת שקיבלתי ירשתי 847 הערות TODO. עזב לפני 3 שנים. אחת מהן אומרת 'צריך לתקן את כל המערכת'. מאז אני חי עם השאלה הזאת.",
        "defendant": "דני, מתכנת לשעבר",
        "charges": ["בגידה חברתית", "עיכוב כרוני", "ייאוש מכוון"],
        "author_id": 7,
        "hours": 240,
    },
]


def _seed(conn: sqlite3.Connection) -> None:
    """Populate users, posts, post_charges and follows. All seed users share password 'demo123'."""
    pwd = hash_password("demo123")
    for name, email, days, bio in SEED_USERS:
        conn.execute(
            "INSERT INTO users (name, email, password_hash, bio, created_at) VALUES (?, ?, ?, ?, ?)",
            (name, email, pwd, bio, _hours_ago(days * 24)),
        )
    for follower_id, followee_id in SEED_FOLLOWS:
        conn.execute(
            "INSERT INTO follows (follower_id, followee_id, created_at) VALUES (?, ?, ?)",
            (follower_id, followee_id, _hours_ago(18 * 24)),
        )
    for post in SEED_POSTS:
        cur = conn.execute(
            "INSERT INTO posts (title, body, defendant, author_id, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (post["title"], post["body"], post["defendant"],
             post["author_id"], _hours_ago(post["hours"])),
        )
        for charge in post["charges"]:
            conn.execute(
                "INSERT INTO post_charges (post_id, charge) VALUES (?, ?)",
                (cur.lastrowid, charge),
            )
    conn.commit()
