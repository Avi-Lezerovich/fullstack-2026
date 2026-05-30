-- LolSuit database schema (SQLite).
-- users 1—N posts, posts 1—N post_charges, users 1—1 sessions.
-- Seed data is inserted from Python (server/app/models.py) so passwords can be hashed.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at    TEXT NOT NULL          -- ISO-8601
);

-- Stateful server-side sessions (lecture 5 design): one active session per user.
-- The client only holds an opaque session_id in an httpOnly cookie.
CREATE TABLE IF NOT EXISTS sessions (
    user_id    INTEGER NOT NULL UNIQUE,
    session_id TEXT    NOT NULL,
    created_at TEXT    NOT NULL,         -- ISO-8601
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_sessions_session ON sessions(session_id);

CREATE TABLE IF NOT EXISTS posts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    title      TEXT NOT NULL,
    body       TEXT NOT NULL,
    defendant  TEXT NOT NULL,
    location   TEXT,                      -- nullable
    author_id  INTEGER NOT NULL,
    created_at TEXT NOT NULL,             -- ISO-8601
    FOREIGN KEY (author_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS post_charges (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id INTEGER NOT NULL,
    charge  TEXT NOT NULL,                -- one of CHARGES_OPTIONS
    FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_posts_author      ON posts(author_id);
CREATE INDEX IF NOT EXISTS idx_post_charges_post ON post_charges(post_id);
