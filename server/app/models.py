"""Database access layer — raw PyMySQL (no ORM), targeting MySQL 8 / Amazon RDS.

Owns the connection helper, schema/seed bootstrap, and the absolute path to the
schema. Seed fixtures are ported from the old client mock so the app shows
identical content.

Connection settings come from the environment so the same image runs against a
local MySQL container or an RDS endpoint:
  DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME
"""
import os
import time
import datetime
from pathlib import Path

import pymysql
from pymysql.cursors import DictCursor

from .utils import hash_password
from .seed_data import SEED_USERS, SEED_FOLLOWS, SEED_POSTS

BASE_DIR = Path(__file__).resolve().parents[2]          # repo root
DATABASE_DIR = BASE_DIR / "database"
SCHEMA_PATH = DATABASE_DIR / "init.sql"
# Uploaded images live next to the server package (override for Docker volumes).
UPLOAD_DIR = os.environ.get("UPLOAD_DIR", str(BASE_DIR / "server" / "uploads"))

DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "localhost"),
    "port": int(os.environ.get("DB_PORT", "3306")),
    "user": os.environ.get("DB_USER", "root"),
    "password": os.environ.get("DB_PASSWORD", ""),
    "database": os.environ.get("DB_NAME", "lolsuit"),
}


class _Connection:
    """sqlite3-style adapter over a PyMySQL connection.

    services.py and the seed code were written against sqlite3's convenience API
    (``conn.execute(sql, params)`` returns a cursor; rows are name-indexable).
    PyMySQL has no ``conn.execute`` and uses ``%s`` placeholders, so this adapter:
      - exposes ``execute`` that opens a DictCursor and runs the statement,
      - rewrites the ``?`` placeholders the callers use into ``%s``,
    and otherwise forwards commit/close. Rows come back as plain dicts, which the
    callers already treat like ``sqlite3.Row`` (``row["col"]``).
    """

    def __init__(self, raw: pymysql.connections.Connection):
        self._raw = raw

    def execute(self, sql: str, params=()):
        cur = self._raw.cursor()
        cur.execute(sql.replace("?", "%s"), tuple(params))
        return cur

    def commit(self) -> None:
        self._raw.commit()

    def close(self) -> None:
        self._raw.close()


def get_db() -> _Connection:
    """Open a connection that yields dict rows; FK enforcement is on by default in InnoDB."""
    raw = pymysql.connect(charset="utf8mb4", cursorclass=DictCursor, autocommit=False, **DB_CONFIG)
    return _Connection(raw)


def _connect_with_retry(cfg: dict, attempts: int = 30, delay: float = 2.0):
    """Open a PyMySQL connection, retrying while the server is still coming up.

    A freshly-started MySQL container (and occasionally an RDS endpoint) refuses
    connections for a few seconds after boot, so we wait instead of crashing.
    """
    last = None
    for _ in range(attempts):
        try:
            return pymysql.connect(charset="utf8mb4", **cfg)
        except pymysql.err.OperationalError as exc:
            last = exc
            time.sleep(delay)
    raise last


def _ensure_database() -> None:
    """Create the target schema (database) if it does not exist yet.

    RDS hands you an empty instance; connecting with ``database=...`` would fail
    until the schema exists, so we first connect without one. ``IF NOT EXISTS``
    keeps this safe on every boot.
    """
    cfg = {k: v for k, v in DB_CONFIG.items() if k != "database"}
    raw = _connect_with_retry(cfg)
    try:
        with raw.cursor() as cur:
            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS `{DB_CONFIG['database']}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        raw.commit()
    finally:
        raw.close()


def init_db() -> None:
    """Create the schema/tables (idempotent) and seed once, if the DB is empty."""
    _ensure_database()
    conn = get_db()
    try:
        with open(SCHEMA_PATH, "r", encoding="utf-8") as fh:
            # PyMySQL runs one statement per execute, so split the script on ';'.
            for stmt in fh.read().split(";"):
                if stmt.strip():
                    conn.execute(stmt)
        conn.commit()
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


def _seed(conn: _Connection) -> None:
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
