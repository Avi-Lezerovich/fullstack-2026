"""Unit tests — post deletion (the pyramid base).

Target under test: server/app/services.py -> delete_post(). Unlike the auth unit
tests (hash_password, session_cookie_flags, get_session_token), this function's
entire job IS storage I/O — there's no pure sub-piece to test in isolation from a
database. So "unit" here means the smallest storage a test can get away with: a
bare in-memory SQLite connection passed straight into the function, with no Flask
app, no HTTP request, no @require_auth, no cookies. That's still Fast (no file
I/O, no process spin-up) and Independent/Repeatable (a fresh :memory: DB per
test) — it just isolates delete_post itself rather than the whole request/response
cycle, which the integration suite (test_post_delete_flow.py) covers instead.

Every test follows Arrange -> Act -> Assert.
"""
import sqlite3

import pytest

from app.services import delete_post

# Minimal schema slice delete_post actually touches (mirrors tests/conftest.py's
# SCHEMA_SQL, trimmed to posts + post_charges since auth tables are irrelevant here).
SCHEMA_SQL = """
CREATE TABLE posts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    title      TEXT NOT NULL,
    author_id  INTEGER NOT NULL
);
CREATE TABLE post_charges (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id INTEGER NOT NULL,
    charge  TEXT NOT NULL,
    FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE
);
"""


@pytest.fixture
def conn():
    """A throwaway in-memory SQLite connection — gone the instant the test ends."""
    raw = sqlite3.connect(":memory:")
    raw.row_factory = sqlite3.Row
    raw.execute("PRAGMA foreign_keys = ON")  # match InnoDB's always-on FK enforcement
    raw.executescript(SCHEMA_SQL)
    yield raw
    raw.close()


def _insert_post(conn, author_id: int, title: str = "כתב אישום") -> int:
    cur = conn.execute(
        "INSERT INTO posts (title, author_id) VALUES (?, ?)", (title, author_id)
    )
    conn.commit()
    return cur.lastrowid


@pytest.mark.unit
def test_delete_post_removes_the_row_and_returns_ok(conn):
    # Arrange — a post that belongs to author 1.
    post_id = _insert_post(conn, author_id=1)

    # Act — that same author deletes it.
    result = delete_post(post_id, author_id=1, conn=conn)

    # Assert — "ok", and the row is actually gone.
    assert result == "ok"
    row = conn.execute("SELECT id FROM posts WHERE id = ?", (post_id,)).fetchone()
    assert row is None


@pytest.mark.unit
def test_delete_post_returns_forbidden_for_a_different_author(conn):
    # Arrange — a post that belongs to author 1.
    post_id = _insert_post(conn, author_id=1)

    # Act — author 2 (not the owner) tries to delete it.
    result = delete_post(post_id, author_id=2, conn=conn)

    # Assert — "forbidden", and — the security-critical part — the post is
    # untouched, not silently deleted anyway.
    assert result == "forbidden"
    row = conn.execute("SELECT id FROM posts WHERE id = ?", (post_id,)).fetchone()
    assert row is not None


@pytest.mark.unit
def test_delete_post_returns_not_found_for_a_missing_post(conn):
    # Act — delete an id that was never inserted.
    result = delete_post(post_id=999, author_id=1, conn=conn)

    # Assert — "not_found", not an exception.
    assert result == "not_found"


@pytest.mark.unit
def test_delete_post_cascades_to_post_charges(conn):
    # Arrange — a post with two charges attached.
    post_id = _insert_post(conn, author_id=1)
    conn.execute("INSERT INTO post_charges (post_id, charge) VALUES (?, ?)", (post_id, "עבירה א'"))
    conn.execute("INSERT INTO post_charges (post_id, charge) VALUES (?, ?)", (post_id, "עבירה ב'"))
    conn.commit()

    # Act — the owner deletes the post.
    result = delete_post(post_id, author_id=1, conn=conn)

    # Assert — the post is gone, and so are its charges (via ON DELETE CASCADE),
    # proving delete_post doesn't need to clean those up itself.
    assert result == "ok"
    charges = conn.execute(
        "SELECT id FROM post_charges WHERE post_id = ?", (post_id,)
    ).fetchall()
    assert charges == []
