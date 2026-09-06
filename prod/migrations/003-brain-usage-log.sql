-- ============================================================================
--  003-brain-usage-log.sql - persisted AI usage history, for a deployment that
--  already has data.
-- ============================================================================
--  WHEN YOU NEED THIS
--
--  On a fresh database you do not: `database/init.sql` already contains the
--  CREATE TABLE, and `init-rds.sh` applies it.
--
--  You need this file when the RDS instance was initialised before the ops
--  dashboard's AI Usage tab. Without the table the application still runs -
--  LAST_CALL in brain/__init__.py keeps answering /api/health exactly as
--  before - but every write to it becomes a no-op (see brain/__init__.py's
--  _log_call, which swallows the failure and logs a warning), and the new
--  admin endpoint has nothing to aggregate.
--
--      cd /opt/lolsuit && git pull
--      cd prod && ./init-rds.sh --check   # confirm the table is really there
--
--  HOW TO APPLY (take an RDS snapshot first - every time):
--
--      docker run --rm -i -e MYSQL_PWD="$DB_PASSWORD" mysql:8.0 \
--        mysql -h "$DB_HOST" -u "$DB_USER" "$DB_NAME" < 003-brain-usage-log.sql
--
--  Safe to re-run: the CREATE is IF NOT EXISTS and there is no backfill - a
--  call made before this table existed was never recorded anywhere, so there
--  is nothing to reconstruct it from.
--
--  Nothing is dropped and no existing table is altered, so rolling back to the
--  previous image is a redeploy rather than a restore: the old code never
--  reads or writes this table.
-- ============================================================================

SET NAMES utf8mb4;

-- The canonical definition lives in database/init.sql, section 24, with the
-- reasoning. Keep the two in step: this file is the deploy path for an
-- existing database, not a second source of truth.

CREATE TABLE IF NOT EXISTS brain_calls (
  id              INT AUTO_INCREMENT PRIMARY KEY,
  task            VARCHAR(32)  NOT NULL,
  provider        VARCHAR(16)  NOT NULL,
  backend         ENUM('llm','offline') NOT NULL,
  success         TINYINT(1)   NOT NULL,
  fallback_reason VARCHAR(300) NULL,
  input_tokens    INT NOT NULL DEFAULT 0,
  output_tokens   INT NOT NULL DEFAULT 0,
  cache_read      INT NOT NULL DEFAULT 0,
  cache_write     INT NOT NULL DEFAULT 0,
  created_at      DATETIME NOT NULL,
  KEY idx_brain_calls_provider_day (provider, created_at),
  KEY idx_brain_calls_task (task, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
