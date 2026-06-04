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
from .seed_data import SEED_USERS, SEED_FOLLOWS, SEED_POSTS

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
