-- LolSuit database schema (MySQL 8.0 / Amazon RDS).
-- users 1—N posts, posts 1—N post_charges, users 1—1 sessions, users M—N users (follows).
-- Seed data is inserted from Python (server/app/models.py) so passwords can be hashed.
-- Tables are created parent-first so the InnoDB foreign keys resolve.

CREATE TABLE IF NOT EXISTS users (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    name          VARCHAR(255)  NOT NULL,
    email         VARCHAR(255)  NOT NULL UNIQUE,
    password_hash VARCHAR(255)  NOT NULL,
    bio           TEXT,                       -- nullable: short self-description
    avatar_url    VARCHAR(1024),              -- nullable: /api/uploads/<file> path
    created_at    VARCHAR(32)   NOT NULL      -- ISO-8601
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Stateful server-side sessions (lecture 5 design): one active session per user.
-- The client only holds an opaque session_id in an httpOnly cookie.
CREATE TABLE IF NOT EXISTS sessions (
    user_id    INT          NOT NULL UNIQUE,
    session_id VARCHAR(255) NOT NULL,
    created_at VARCHAR(32)  NOT NULL,         -- ISO-8601
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_sessions_session (session_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS posts (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    title      VARCHAR(512)  NOT NULL,
    body       TEXT          NOT NULL,        -- sanitized rich-text HTML
    defendant  VARCHAR(255)  NOT NULL,
    image_url  VARCHAR(1024),                 -- nullable: /api/uploads/<file> path
    author_id  INT           NOT NULL,
    created_at VARCHAR(32)   NOT NULL,        -- ISO-8601
    FOREIGN KEY (author_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_posts_author (author_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Directed follow graph: (follower_id) follows (followee_id). M—N on users.
CREATE TABLE IF NOT EXISTS follows (
    follower_id INT         NOT NULL,
    followee_id INT         NOT NULL,
    created_at  VARCHAR(32) NOT NULL,         -- ISO-8601
    PRIMARY KEY (follower_id, followee_id),
    FOREIGN KEY (follower_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (followee_id) REFERENCES users(id) ON DELETE CASCADE,
    CHECK (follower_id <> followee_id),
    INDEX idx_follows_follower (follower_id),
    INDEX idx_follows_followee (followee_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS post_charges (
    id      INT AUTO_INCREMENT PRIMARY KEY,
    post_id INT          NOT NULL,
    charge  VARCHAR(255) NOT NULL,            -- one of CHARGES_OPTIONS
    FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE,
    INDEX idx_post_charges_post (post_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
