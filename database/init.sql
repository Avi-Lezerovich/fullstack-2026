-- LolSuit database schema (SQLite).
-- users 1—N posts, posts 1—N post_charges, users 1—1 sessions, users M—N users (follows).
-- Seed data is inserted from Python (server/app/models.py) so passwords can be hashed.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    bio           TEXT,                  -- nullable: short self-description
    avatar_url    TEXT,                  -- nullable: /api/uploads/<file> path
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
    body       TEXT NOT NULL,             -- sanitized rich-text HTML
    defendant  TEXT NOT NULL,
    image_url  TEXT,                      -- nullable: /api/uploads/<file> path
    author_id  INTEGER NOT NULL,
    created_at TEXT NOT NULL,             -- ISO-8601
    FOREIGN KEY (author_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Directed follow graph: (follower_id) follows (followee_id). M—N on users.
CREATE TABLE IF NOT EXISTS follows (
    follower_id INTEGER NOT NULL,
    followee_id INTEGER NOT NULL,
    created_at  TEXT    NOT NULL,         -- ISO-8601
    PRIMARY KEY (follower_id, followee_id),
    FOREIGN KEY (follower_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (followee_id) REFERENCES users(id) ON DELETE CASCADE,
    CHECK (follower_id <> followee_id)
);

CREATE INDEX IF NOT EXISTS idx_follows_follower ON follows(follower_id);
CREATE INDEX IF NOT EXISTS idx_follows_followee ON follows(followee_id);

CREATE TABLE IF NOT EXISTS post_charges (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id INTEGER NOT NULL,
    charge  TEXT NOT NULL,                -- one of CHARGES_OPTIONS
    FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_posts_author      ON posts(author_id);
CREATE INDEX IF NOT EXISTS idx_post_charges_post ON post_charges(post_id);
