-- ============================================================================
--  004-brain-credentials.sql - per-credential and per-model AI accounting,
--  for a deployment that already has data.
-- ============================================================================
--  WHEN YOU NEED THIS
--
--  On a fresh database you do not: `database/init.sql` already declares these
--  columns, and `init-rds.sh` applies it.
--
--  You need this file when the RDS instance was initialised before the brain
--  learned to talk to more than one credential. Without the columns the
--  application still runs - `_log_call` in brain/__init__.py swallows the
--  failure and logs a warning, exactly as it did before 003 - but every usage
--  row is lost rather than merely unattributed, so the AI tab goes blank
--  instead of degrading.
--
--  WHY EACH PIECE
--
--  `credential` is which key answered, not which vendor: 'api1-gemini' rather
--  than 'gemini'. Rows written before this migration keep the empty string,
--  and every read uses COALESCE(NULLIF(credential,''), provider) - so a
--  pre-migration row shows up on the board under its provider name, beside
--  the new labels, with no backfill and no lying about which key it was.
--
--  `model` is the same argument one level down. The free-tier allowance is a
--  property of the model, not of the provider, so "how many Gemini calls
--  today" is not a question with an answer until the model is recorded.
--
--  `latency_ms` is added now because the table is being altered anyway, and
--  "which credential is slow" is the question immediately after "which
--  credential works".
--
--  `fallback_reason` widens because 300 was sized for
--  "ModuleNotFoundError: No module named 'anthropic'". Google's error bodies
--  name the model, the quota metric and a retry delay, and run well past it -
--  and since 4.x those bodies are actually read rather than discarded. Both
--  300 and 500 take a 2-byte length prefix at utf8mb4, so this is in-place.
--
--  NOT IDEMPOTENT. Unlike 003, which is a CREATE TABLE IF NOT EXISTS, an
--  ALTER ... ADD COLUMN fails on a second run. Run it once. If you are unsure
--  whether it has been applied, look before you leap:
--
--      SELECT COLUMN_NAME FROM information_schema.COLUMNS
--       WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'brain_calls';
--
--  HOW TO APPLY (take an RDS snapshot first - every time):
--
--      mysql -h "$DB_HOST" -u "$DB_USER" -p "$DB_NAME" < 004-brain-credentials.sql
-- ============================================================================

SET NAMES utf8mb4;

-- Appended rather than positioned. An `AFTER provider` would be tidier to read
-- in a DESCRIBE and would force a full table rebuild to get it; appending
-- keeps ALGORITHM=INSTANT, which on a table the worker writes to every tick is
-- the difference between a deploy and an outage.
ALTER TABLE brain_calls
  ADD COLUMN credential VARCHAR(48) NOT NULL DEFAULT '',
  ADD COLUMN model      VARCHAR(64) NOT NULL DEFAULT '',
  ADD COLUMN latency_ms INT         NOT NULL DEFAULT 0,
  ALGORITHM=INSTANT;

ALTER TABLE brain_calls
  MODIFY COLUMN fallback_reason VARCHAR(500) NULL;

-- The chain's own question, asked once a minute per process: "how many calls
-- has each credential made since UTC midnight". created_at leads because the
-- WHERE is the range and the GROUP BY is the tail.
ALTER TABLE brain_calls
  ADD KEY idx_brain_calls_day_credential (created_at, credential);
