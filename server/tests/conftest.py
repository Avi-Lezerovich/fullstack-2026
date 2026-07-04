"""Shared pytest fixtures.

The integration tests want to exercise the REAL Flask endpoints (routes + utils +
services + storage) but without a live MySQL server — that keeps them Fast,
Independent and Repeatable (F.I.R.S.T.). We do that the way the lecture recommends:
inject the storage boundary. The app already supports it (`services.get_db`), so we
swap MySQL for a throwaway SQLite database and patch `get_db` to return it.

Only two things differ between MySQL and SQLite on the auth path, and the adapter
below hides both: the placeholder style (`?` works natively in SQLite) and the
sessions upsert (`ON DUPLICATE KEY UPDATE` → SQLite's `ON CONFLICT`).

KNOWN PARITY LIMITS (deliberate trade-offs, covered by the Cypress E2E which runs
against real MySQL):
  - The literal MySQL upsert text in services.create_session is rewritten, so the
    MySQL dialect itself is never parsed by these tests.
  - The production `?` -> `%s` placeholder rewrite (app/models.py _Connection)
    does not run here; SQLite consumes `?` directly.
"""
import re
import sqlite3

import pytest

# SQLite-dialect mirror of database/init.sql (AUTO_INCREMENT/ENGINE/CHARSET dropped,
# UNIQUE/FK kept). sessions.user_id stays UNIQUE so the create_session upsert works.
SCHEMA_SQL = """
CREATE TABLE users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    bio           TEXT,
    avatar_url    TEXT,
    created_at    TEXT NOT NULL
);
CREATE TABLE sessions (
    user_id    INTEGER NOT NULL UNIQUE,
    session_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE TABLE posts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    title      TEXT NOT NULL,
    body       TEXT NOT NULL,
    defendant  TEXT NOT NULL,
    image_url  TEXT,
    author_id  INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (author_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE TABLE post_charges (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id INTEGER NOT NULL,
    charge  TEXT NOT NULL,
    FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE
);
CREATE TABLE follows (
    follower_id INTEGER NOT NULL,
    followee_id INTEGER NOT NULL,
    created_at  TEXT NOT NULL,
    PRIMARY KEY (follower_id, followee_id),
    FOREIGN KEY (follower_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (followee_id) REFERENCES users(id) ON DELETE CASCADE
);
"""


def _to_sqlite(sql: str) -> str:
    """Rewrite the MySQL-only bits of the app's SQL into SQLite dialect.

    The auth code only has one MySQL-ism — the sessions upsert in create_session:
        ... ON DUPLICATE KEY UPDATE session_id = VALUES(session_id), ...
    becomes SQLite's:
        ... ON CONFLICT(user_id) DO UPDATE SET session_id = excluded.session_id, ...
    (`INSERT IGNORE` is handled too, for completeness with the follows code.)
    Placeholders stay as `?` — SQLite uses them natively.
    """
    if "ON DUPLICATE KEY UPDATE" in sql:
        sql = sql.replace("ON DUPLICATE KEY UPDATE", "ON CONFLICT(user_id) DO UPDATE SET")
        sql = re.sub(r"VALUES\((\w+)\)", r"excluded.\1", sql)  # VALUES(col) -> excluded.col
    sql = sql.replace("INSERT IGNORE", "INSERT OR IGNORE")
    return sql


class SqliteConn:
    """Drop-in stand-in for app.models._Connection, backed by SQLite.

    Mirrors the exact surface services.py relies on: execute()/commit()/close(),
    a cursor whose rows are name-indexable (row["col"]) and expose lastrowid.
    """

    def __init__(self, raw: sqlite3.Connection):
        raw.row_factory = sqlite3.Row  # so row["col"] works, like DictCursor / sqlite3.Row
        # SQLite ships with FK enforcement OFF; production MySQL/InnoDB always
        # enforces it, so switch it on to keep the stand-in honest.
        raw.execute("PRAGMA foreign_keys = ON")
        self._raw = raw

    def execute(self, sql: str, params=()):
        cur = self._raw.cursor()
        cur.execute(_to_sqlite(sql), tuple(params))
        return cur

    def commit(self) -> None:
        self._raw.commit()

    def close(self) -> None:
        self._raw.close()


@pytest.fixture
def db_path(tmp_path):
    """A fresh, schema-loaded SQLite file per test (Independent + Repeatable)."""
    path = tmp_path / "auth_test.db"
    con = sqlite3.connect(path)
    con.executescript(SCHEMA_SQL)
    con.commit()
    con.close()
    return str(path)


@pytest.fixture
def client(db_path, monkeypatch):
    """A Flask test client wired to the throwaway SQLite DB (no MySQL needed).

    Each service call opens its own short-lived connection via get_db(); pointing
    them all at the same temp *file* means writes from one call are visible to the
    next — exactly like the real per-request connections against MySQL.
    """
    def fake_get_db():
        return SqliteConn(sqlite3.connect(db_path))

    # services.py did `from .models import get_db`, so patch it in the services module.
    monkeypatch.setattr("app.services.get_db", fake_get_db)
    # create_app() calls init_db(), which would connect to MySQL — make it a no-op
    # (our fixture already created the schema).
    monkeypatch.setattr("app.init_db", lambda: None)

    from app import create_app

    flask_app = create_app()
    flask_app.config.update(TESTING=True)
    return flask_app.test_client()
