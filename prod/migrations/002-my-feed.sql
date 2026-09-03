-- ============================================================================
--  002-my-feed.sql - the followed-lawsuits feed, for a deployment that already
--  has data.
-- ============================================================================
--  WHEN YOU NEED THIS
--
--  On a fresh database you do not: `database/init.sql` already contains both
--  CREATE TABLE statements, and `init-rds.sh` applies it.
--
--  You need this file when the RDS instance was initialised BEFORE "My Feed",
--  which is every deployment made before v2.2.0. Without the two tables the
--  application starts and serves the public feed as usual, then answers 500 on
--  `GET /api/cases/feed` and on the first comment posted to any case - the
--  activity bump runs inside the same transaction as the comment, so a missing
--  table takes the comment down with it.
--
--      cd /opt/lolsuit && git pull        # <- the step that is easy to skip
--      cd prod && ./init-rds.sh --check   # confirm the tables are really there
--
--  HOW TO APPLY (take an RDS snapshot first - every time):
--
--      docker run --rm -i -e MYSQL_PWD="$DB_PASSWORD" mysql:8.0 \
--        mysql -h "$DB_HOST" -u "$DB_USER" "$DB_NAME" < 002-my-feed.sql
--
--  Safe to re-run: both CREATEs are IF NOT EXISTS and every backfill is an
--  INSERT ... SELECT guarded by ON DUPLICATE KEY UPDATE.
--
--  Nothing is dropped and no existing table is altered, so rolling back to the
--  previous image is a redeploy rather than a restore: the old code simply
--  never reads either table.
-- ============================================================================

SET NAMES utf8mb4;

-- The canonical definitions live in database/init.sql, sections 22 and 23,
-- with the reasoning. Keep the two in step: this file is the deploy path for
-- an existing database, not a second source of truth.

CREATE TABLE IF NOT EXISTS case_follows (
  case_id    INT      NOT NULL,
  user_id    INT      NOT NULL,
  source     ENUM('auto','manual') NOT NULL DEFAULT 'manual',
  created_at DATETIME NOT NULL,
  PRIMARY KEY (case_id, user_id),
  CONSTRAINT fk_follows_case FOREIGN KEY (case_id) REFERENCES cases(id) ON DELETE CASCADE,
  CONSTRAINT fk_follows_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  KEY idx_follows_user (user_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS case_activity (
  case_id            INT         NOT NULL PRIMARY KEY,
  last_activity_at   DATETIME    NULL,
  last_activity_kind VARCHAR(24) NOT NULL,
  CONSTRAINT fk_activity_case FOREIGN KEY (case_id) REFERENCES cases(id) ON DELETE CASCADE,
  KEY idx_activity_recent (last_activity_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- --- give every existing case an activity timestamp -------------------------
--
-- Reconstructed from the evidence that survives: the newest of the filing, the
-- verdict, the close, and the last publicly visible comment. Once the new code
-- is running `touch()` keeps it current; this only has to be good enough that
-- an old case does not sort above a live one on day one.
INSERT INTO case_activity (case_id, last_activity_at, last_activity_kind)
SELECT c.id,
       GREATEST(
         c.filed_at,
         COALESCE(c.verdict_at, c.filed_at),
         COALESCE(c.closed_at, c.filed_at),
         COALESCE((SELECT MAX(cm.created_at) FROM comments cm
                   WHERE cm.case_id = c.id
                     AND cm.moderation_status IN ('published','flagged')), c.filed_at)
       ),
       CASE WHEN c.closed_at  IS NOT NULL THEN 'closed'
            WHEN c.verdict_at IS NOT NULL THEN 'verdict'
            ELSE 'filed' END
FROM cases c
ON DUPLICATE KEY UPDATE case_activity.case_id = case_activity.case_id;

-- --- follow the cases people are already party to ----------------------------
--
-- The same three automatic rules the application applies from now on, applied
-- once to the history: you filed it, you were named as its defendant, or you
-- testified in it. Marked 'auto' so an unfollow reads as a deliberate choice.
INSERT INTO case_follows (case_id, user_id, source, created_at)
SELECT c.id, c.author_id, 'auto', UTC_TIMESTAMP()
FROM cases c
ON DUPLICATE KEY UPDATE case_follows.case_id = case_follows.case_id;

INSERT INTO case_follows (case_id, user_id, source, created_at)
SELECT c.id, c.defendant_user_id, 'auto', UTC_TIMESTAMP()
FROM cases c
WHERE c.defendant_user_id IS NOT NULL
ON DUPLICATE KEY UPDATE case_follows.case_id = case_follows.case_id;

INSERT INTO case_follows (case_id, user_id, source, created_at)
SELECT ws.case_id, ws.witness_user_id, 'auto', UTC_TIMESTAMP()
FROM witness_summons ws
WHERE ws.status = 'testified'
ON DUPLICATE KEY UPDATE case_follows.case_id = case_follows.case_id;
