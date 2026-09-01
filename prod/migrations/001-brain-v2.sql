-- ============================================================================
--  001-brain-v2.sql - the episodic memory tables, for a deployment that
--  already has data.
-- ============================================================================
--  WHEN YOU NEED THIS
--
--  On a fresh database you do not: `database/init.sql` already contains both
--  CREATE TABLE statements, and `init-rds.sh` applies it.
--
--  You need this file when the RDS instance was initialised BEFORE brain v2,
--  or - the case that actually bit us on the v1.2.0 deploy - when `init-rds.sh`
--  ran against a STALE CHECKOUT on the box. That script reads init.sql from the
--  EC2 instance's own working copy, so an un-pulled repo silently applies the
--  old schema and reports success. The application then starts, serves every
--  page, and fails only inside the worker, where nobody is looking.
--
--      cd /opt/lolsuit && git pull        # <- the step that is easy to skip
--      cd prod && ./init-rds.sh --check   # confirm the tables are really there
--
--  HOW TO APPLY (take an RDS snapshot first - every time):
--
--      docker run --rm -i -e MYSQL_PWD="$DB_PASSWORD" mysql:8.0 \
--        mysql -h "$DB_HOST" -u "$DB_USER" "$DB_NAME" < 001-brain-v2.sql
--
--  Safe to re-run: both CREATEs are IF NOT EXISTS and the backfill is an
--  INSERT ... SELECT guarded by ON DUPLICATE KEY UPDATE.
--
--  This file does NOT drop `bot_memories`. The application reads the new table
--  and clears both on "forget me", so the old one is inert but intact - which
--  is what makes a rollback to the previous image a redeploy rather than a
--  restore. Drop it by hand, once, after brain v2 has run for a while:
--
--      DROP TABLE bot_memories;
-- ============================================================================

SET NAMES utf8mb4;

-- The canonical definitions live in database/init.sql, sections 20 and 21,
-- with the reasoning. Keep the two in step: this file is the deploy path for
-- an existing database, not a second source of truth.

CREATE TABLE IF NOT EXISTS agent_events (
  id              INT AUTO_INCREMENT PRIMARY KEY,
  agent_user_id   INT NOT NULL,
  kind            VARCHAR(32) NOT NULL,
  case_id         INT NULL,
  subject_user_id INT NULL,
  summary         VARCHAR(500) NOT NULL,
  importance      TINYINT NOT NULL DEFAULT 1,
  dedupe_key      VARCHAR(64) NULL,
  created_at      DATETIME NOT NULL,
  CONSTRAINT fk_event_agent FOREIGN KEY (agent_user_id) REFERENCES users(id) ON DELETE CASCADE,
  CONSTRAINT fk_event_case FOREIGN KEY (case_id) REFERENCES cases(id) ON DELETE CASCADE,
  CONSTRAINT fk_event_subject FOREIGN KEY (subject_user_id) REFERENCES users(id) ON DELETE CASCADE,
  UNIQUE KEY uq_event_dedupe (dedupe_key),
  KEY idx_event_agent_recent (agent_user_id, created_at),
  KEY idx_event_agent_subject (agent_user_id, subject_user_id, created_at),
  KEY idx_event_case (case_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS agent_memories (
  id               INT AUTO_INCREMENT PRIMARY KEY,
  agent_user_id    INT NOT NULL,
  subject_id       INT NOT NULL,
  summary          TEXT NULL,
  facts            JSON NULL,
  covered_event_id INT NOT NULL DEFAULT 0,
  updated_at       DATETIME NOT NULL,
  CONSTRAINT fk_agent_memory_agent FOREIGN KEY (agent_user_id) REFERENCES users(id) ON DELETE CASCADE,
  CONSTRAINT fk_agent_memory_subject FOREIGN KEY (subject_id) REFERENCES users(id) ON DELETE CASCADE,
  UNIQUE KEY uq_agent_memory (agent_user_id, subject_id),
  KEY idx_agent_memory_subject (subject_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- --- carry the old memories across ------------------------------------------
--
-- Every bot_memories row carries straight across. `covered_event_id` starts at 0 rather than at the old
-- `covered_message_id`: the two count different things, and 0 simply means
-- "no episodes folded in yet", which is true and self-correcting - the next
-- consolidation picks up everything since.
INSERT INTO agent_memories
  (agent_user_id, subject_id, summary, facts, covered_event_id, updated_at)
SELECT agent_user_id, subject_user_id, summary, facts, 0, updated_at
FROM bot_memories
ON DUPLICATE KEY UPDATE agent_memories.agent_user_id = agent_memories.agent_user_id;
