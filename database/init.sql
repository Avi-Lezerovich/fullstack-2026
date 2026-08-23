-- ============================================================================
--  LolSuit — database schema
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
--  free of triggers, stored procedures and DELIMITER blocks — a test asserts it.
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
-- 1. users — humans and bots alike. A bot is a user plus an `agents` row, so
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