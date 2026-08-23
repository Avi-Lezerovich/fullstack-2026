-- ============================================================================
--  LolSuit - database schema
-- ============================================================================
--  Mounted into the MySQL container at /docker-entrypoint-initdb.d/01-init.sql,
--  so the schema exists before the API ever connects. The application never
--  creates tables at boot: create_app() has zero side effects.
--
--  NOTE: /docker-entrypoint-initdb.d only runs on an EMPTY data volume. After
--  editing this file you must `docker compose down -v && docker compose up -d`.
--
--  The test suite executes this exact file against its own schema, so the tests
--  exercise the real MySQL dialect. That is only possible while this file stays
--  free of triggers, stored procedures and DELIMITER blocks - a test asserts it.
--
--  Conventions
--    * All timestamps are DATETIME holding NAIVE UTC, written with
--      UTC_TIMESTAMP(). There is exactly one clock: the database's.
--    * InnoDB + utf8mb4 throughout (the UI is Hebrew).
--    * Uniqueness that matters is enforced HERE, not only in Python.
-- ============================================================================

SET NAMES utf8mb4;
SET time_zone = '+00:00';

-- ---------------------------------------------------------------------------
-- 1. users - humans and bots alike. A bot is a user plus an `agents` row, so
--    bots get real profiles and can be searched, liked and messaged.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
  id             INT AUTO_INCREMENT PRIMARY KEY,
  name           VARCHAR(255)  NOT NULL,
  email          VARCHAR(255)  NOT NULL,
  password_hash  VARCHAR(255)  NOT NULL,
  bio            TEXT          NULL,
  avatar_url     VARCHAR(1024) NULL,
  is_admin       TINYINT(1)    NOT NULL DEFAULT 0,
  -- Denormalised from `agents` purely so witness-eligibility ("no bots") is a
  -- single indexed lookup instead of a join on every summons attempt.
  is_bot         TINYINT(1)    NOT NULL DEFAULT 0,
  status         ENUM('active','banned') NOT NULL DEFAULT 'active',
  banned_at      DATETIME      NULL,
  created_at     DATETIME      NOT NULL,
  UNIQUE KEY uq_users_email (email),
  KEY idx_users_bot (is_bot),
  KEY idx_users_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------------
-- 2. agents - the bot side of a user: role, personality, and behaviour dials.
--    12 jurors + 4 judges + 3 moderators = 19.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS agents (
  user_id               INT NOT NULL PRIMARY KEY,
  role                  ENUM('juror','judge','moderator') NOT NULL,
  -- Only meaningful for role='moderator'.
  moderator_kind        ENUM('sweeper','clerk','arbiter') NULL,
  personality_name      VARCHAR(100) NOT NULL,
  personality_prompt    TEXT         NOT NULL,
  -- Selects the phrase bank the offline generator draws from.
  tone_tag              VARCHAR(32)  NOT NULL,
  -- Juror dial: probability mass toward a guilty vote, blended with charge
  -- severity by brain.decide.decide_vote().
  guilt_bias            DECIMAL(3,2) NOT NULL DEFAULT 0.50,
  -- Judge dial: how this judge breaks a tied jury. Deterministic, so it is
  -- testable rather than random.
  tiebreak_lean         ENUM('guilty','not_guilty') NULL,
  is_active             TINYINT(1)   NOT NULL DEFAULT 1,
  -- All idle-social pacing state lives here, so a worker restart neither
  -- floods the feed nor stalls it.
  --
  -- MICROSECOND precision, deliberately. Bots are selected least-recently-
  -- active first, and at whole-second resolution several bots stamped inside
  -- the same second compare equal - at which point MySQL returns whichever
  -- row the index reaches first and one bot monopolises the rotation.
  last_social_action_at DATETIME(6)  NULL,
  CONSTRAINT fk_agents_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  KEY idx_agents_role (role, is_active),
  KEY idx_agents_social (last_social_action_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------------
-- 3. sessions - MANY rows per user (v1 allowed only one, which cannot express
--    "revoke all sessions"). The cookie carries the raw token; only its
--    SHA-256 is stored, so a database leak does not hand over live sessions.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sessions (
  id           INT AUTO_INCREMENT PRIMARY KEY,
  user_id      INT       NOT NULL,
  token_hash   CHAR(64)  NOT NULL,
  created_at   DATETIME  NOT NULL,
  expires_at   DATETIME  NOT NULL,
  last_seen_at DATETIME  NULL,
  CONSTRAINT fk_sessions_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  UNIQUE KEY uq_sessions_token (token_hash),
  KEY idx_sessions_user (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
