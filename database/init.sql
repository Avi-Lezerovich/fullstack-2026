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
--    20 jurors + 8 judges + 3 moderators = 31.
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

-- ---------------------------------------------------------------------------
-- 4. password_resets - single-use, hashed at rest, short-lived.
--    "Single use" is a guarded UPDATE whose rowcount is checked, never a
--    read-then-write (which would race).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS password_resets (
  id         INT AUTO_INCREMENT PRIMARY KEY,
  user_id    INT      NOT NULL,
  token_hash CHAR(64) NOT NULL,
  created_at DATETIME NOT NULL,
  expires_at DATETIME NOT NULL,
  used_at    DATETIME NULL,
  CONSTRAINT fk_resets_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  UNIQUE KEY uq_resets_token (token_hash),
  KEY idx_resets_user (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS cases (
  id                 INT AUTO_INCREMENT PRIMARY KEY,
  title              VARCHAR(512)  NOT NULL,
  body               TEXT          NOT NULL,
  author_id          INT           NOT NULL,
  defendant_text     VARCHAR(255)  NOT NULL,
  defendant_user_id  INT           NULL,
  image_url          VARCHAR(1024) NULL,

  -- --- trial state machine ------------------------------------------------
  status             ENUM('filed','witness_phase','jury_deliberation',
                          'verdict_reached','closed') NOT NULL DEFAULT 'filed',
  -- When the CURRENT phase ends. The worker's entire job is "find rows whose
  -- deadline has passed", so this column plus idx_cases_due is the hot path.
  phase_deadline_at  DATETIME      NULL,
  filed_at           DATETIME      NOT NULL,
  verdict            ENUM('guilty','not_guilty') NULL,
  sentence_text      TEXT          NULL,
  verdict_at         DATETIME      NULL,
  closed_at          DATETIME      NULL,

  -- --- moderation ---------------------------------------------------------
  -- 'flagged' is still publicly visible (borderline content stays up, marked);
  -- 'hidden'/'rejected' are not. Nothing is ever DELETEd.
  moderation_status  ENUM('published','flagged','hidden','rejected')
                     NOT NULL DEFAULT 'published',
  scanned_at         DATETIME      NULL,

  created_at         DATETIME      NOT NULL,
  CONSTRAINT fk_cases_author FOREIGN KEY (author_id) REFERENCES users(id) ON DELETE CASCADE,
  -- SET NULL, not CASCADE: deleting a user must not erase the lawsuits filed
  -- against them, only detach the link.
  --
  -- "You cannot sue yourself" would naturally be a CHECK here, but MySQL 8
  -- rejects any CHECK over a column that a foreign key's referential action
  -- also writes (error 3823). The referential action is worth more than the
  -- CHECK, so the rule lives in cases_service.create_case() instead and is
  -- covered by tests/unit/test_cases_rules.py.
  KEY idx_cases_due (status, phase_deadline_at),
  KEY idx_cases_feed (moderation_status, created_at),
  KEY idx_cases_author (author_id),
  KEY idx_cases_defendant (defendant_user_id),
  KEY idx_cases_unscanned (scanned_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------------
-- 6. case_charges - the satirical charge chips on a filing.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS case_charges (
  id      INT AUTO_INCREMENT PRIMARY KEY,
  case_id INT         NOT NULL,
  charge  VARCHAR(64) NOT NULL,
  CONSTRAINT fk_charges_case FOREIGN KEY (case_id) REFERENCES cases(id) ON DELETE CASCADE,
  UNIQUE KEY uq_charges (case_id, charge)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------------
-- 7. comments - ONE table for every kind of utterance on a case. `role` tells
--    a regular comment from witness testimony, juror deliberation and the
--    judge's verdict. The UI styles by role; the storage is uniform.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS comments (
  id                INT AUTO_INCREMENT PRIMARY KEY,
  case_id           INT NOT NULL,
  author_id         INT NOT NULL,
  parent_comment_id INT NULL,
  -- Top-level ancestor, so one indexed query fetches and orders a whole
  -- thread without a recursive CTE.
  root_comment_id   INT NULL,
  depth             TINYINT NOT NULL DEFAULT 0,
  body              TEXT NOT NULL,
  role              ENUM('user','witness_testimony','jury_deliberation','verdict')
                    NOT NULL DEFAULT 'user',
  moderation_status ENUM('published','flagged','hidden','rejected')
                    NOT NULL DEFAULT 'published',
  scanned_at        DATETIME NULL,

  -- THE crash-safety primitive. Bot-authored comments carry a deterministic
  -- key ('jury:<member_id>', 'verdict:<case_id>'); a worker that dies after
  -- INSERT but before recording the vote cannot post a second copy, because
  -- the retry hits this UNIQUE. Human comments leave it NULL, and MySQL
  -- permits unlimited NULLs in a UNIQUE index.
  dedupe_key        VARCHAR(64) NULL,

  created_at        DATETIME NOT NULL,
  CONSTRAINT fk_comments_case FOREIGN KEY (case_id) REFERENCES cases(id) ON DELETE CASCADE,
  CONSTRAINT fk_comments_author FOREIGN KEY (author_id) REFERENCES users(id) ON DELETE CASCADE,
  CONSTRAINT fk_comments_parent FOREIGN KEY (parent_comment_id) REFERENCES comments(id) ON DELETE CASCADE,
  UNIQUE KEY uq_comments_dedupe (dedupe_key),
  KEY idx_comments_case (case_id, created_at),
  KEY idx_comments_thread (case_id, root_comment_id, created_at),
  KEY idx_comments_parent (parent_comment_id),
  KEY idx_comments_role (case_id, role),
  KEY idx_comments_unscanned (scanned_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------------
-- 8. likes - the composite PRIMARY KEY *is* the "one like per user" rule.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS likes (
  case_id    INT      NOT NULL,
  user_id    INT      NOT NULL,
  created_at DATETIME NOT NULL,
  PRIMARY KEY (case_id, user_id),
  CONSTRAINT fk_likes_case FOREIGN KEY (case_id) REFERENCES cases(id) ON DELETE CASCADE,
  CONSTRAINT fk_likes_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  KEY idx_likes_user (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------------
-- 9. witness_summons - humans only, max 3 per side, during the witness phase.
--    `deadline_at` is copied from the case so a summons row is self-describing.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS witness_summons (
  id                   INT AUTO_INCREMENT PRIMARY KEY,
  case_id              INT NOT NULL,
  witness_user_id      INT NOT NULL,
  summoned_by_user_id  INT NOT NULL,
  side                 ENUM('plaintiff','defense') NOT NULL,
  status               ENUM('pending','testified','no_show') NOT NULL DEFAULT 'pending',
  summoned_at          DATETIME NOT NULL,
  deadline_at          DATETIME NOT NULL,
  responded_at         DATETIME NULL,
  testimony_comment_id INT NULL,
  CONSTRAINT fk_summons_case FOREIGN KEY (case_id) REFERENCES cases(id) ON DELETE CASCADE,
  CONSTRAINT fk_summons_witness FOREIGN KEY (witness_user_id) REFERENCES users(id) ON DELETE CASCADE,
  CONSTRAINT fk_summons_by FOREIGN KEY (summoned_by_user_id) REFERENCES users(id) ON DELETE CASCADE,
  CONSTRAINT fk_summons_comment FOREIGN KEY (testimony_comment_id) REFERENCES comments(id) ON DELETE SET NULL,
  -- "No duplicates" enforced by the database, not merely by Python.
  UNIQUE KEY uq_summons_case_witness (case_id, witness_user_id),
  KEY idx_summons_case_side (case_id, side),
  KEY idx_summons_witness (witness_user_id, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------------
-- 10. jury_panels - one panel per case. case_id as the PRIMARY KEY makes panel
--     creation idempotent for free: a second worker attempting the same
--     transition hits a duplicate-key and rolls back.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS jury_panels (
  case_id         INT NOT NULL PRIMARY KEY,
  judge_user_id   INT NOT NULL,
  drawn_at        DATETIME NOT NULL,
  tally_guilty    TINYINT NULL,
  tally_not_guilty TINYINT NULL,
  tallied_at      DATETIME NULL,
  tiebreak_used   TINYINT(1) NOT NULL DEFAULT 0,
  CONSTRAINT fk_panels_case FOREIGN KEY (case_id) REFERENCES cases(id) ON DELETE CASCADE,
  CONSTRAINT fk_panels_judge FOREIGN KEY (judge_user_id) REFERENCES users(id),
  KEY idx_panels_judge (judge_user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------------
-- 11. jury_panel_members - the 7 seated jurors.
--     `speaks_at` is the staggering: each juror is given an absolute moment
--     inside the deliberation window at draw time, so the schedule survives a
--     worker crash with no in-memory state. `spoke_at IS NULL` is the claim.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS jury_panel_members (
  id             INT AUTO_INCREMENT PRIMARY KEY,
  case_id        INT NOT NULL,
  juror_user_id  INT NOT NULL,
  seat           TINYINT NOT NULL,
  speaks_at      DATETIME NOT NULL,
  spoke_at       DATETIME NULL,
  vote           ENUM('guilty','not_guilty') NULL,
  comment_id     INT NULL,
  CONSTRAINT fk_members_panel FOREIGN KEY (case_id) REFERENCES jury_panels(case_id) ON DELETE CASCADE,
  CONSTRAINT fk_members_juror FOREIGN KEY (juror_user_id) REFERENCES users(id),
  CONSTRAINT fk_members_comment FOREIGN KEY (comment_id) REFERENCES comments(id) ON DELETE SET NULL,
  UNIQUE KEY uq_members_juror (case_id, juror_user_id),
  UNIQUE KEY uq_members_seat (case_id, seat),
  KEY idx_jurors_due (spoke_at, speaks_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------------
-- 12. reports - the human report queue, worked by the clerk and arbiter bots
--     and overridable by a human admin.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS reports (
  id              INT AUTO_INCREMENT PRIMARY KEY,
  target_type     ENUM('case','comment') NOT NULL,
  target_id       INT NOT NULL,
  reported_by     INT NOT NULL,
  reason          VARCHAR(64) NOT NULL,
  details         TEXT NULL,
  status          ENUM('open','claimed','resolved_hidden',
                       'resolved_dismissed','resolved_banned')
                  NOT NULL DEFAULT 'open',
  claimed_by      INT NULL,
  claimed_at      DATETIME NULL,
  resolved_by     INT NULL,
  resolved_at     DATETIME NULL,
  resolution_note VARCHAR(255) NULL,
  created_at      DATETIME NOT NULL,
  CONSTRAINT fk_reports_reporter FOREIGN KEY (reported_by) REFERENCES users(id) ON DELETE CASCADE,
  CONSTRAINT fk_reports_claimer FOREIGN KEY (claimed_by) REFERENCES users(id) ON DELETE SET NULL,
  CONSTRAINT fk_reports_resolver FOREIGN KEY (resolved_by) REFERENCES users(id) ON DELETE SET NULL,
  -- One report per person per target: no report spam, no queue flooding.
  UNIQUE KEY uq_reports_once (target_type, target_id, reported_by),
  KEY idx_reports_queue (status, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------------
-- 13. moderation_scans - every sentiment verdict ever produced, whatever
--     triggered it. Purely a record; the decision lives on the target's
--     moderation_status.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS moderation_scans (
  id            INT AUTO_INCREMENT PRIMARY KEY,
  target_type   ENUM('case','comment') NOT NULL,
  target_id     INT NOT NULL,
  source        ENUM('publish','sweep','report') NOT NULL,
  label         ENUM('ok','borderline','toxic') NOT NULL,
  score         DECIMAL(4,3) NOT NULL DEFAULT 0.000,
  matched_terms VARCHAR(255) NULL,
  scanned_at    DATETIME NOT NULL,
  KEY idx_scans_target (target_type, target_id),
  KEY idx_scans_label (label, scanned_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------------
-- 14. moderation_actions - the audit trail. This is what makes "a human admin
--     can override any bot decision" *auditable*: an override records both the
--     previous and the new status alongside who did it.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS moderation_actions (
  id              INT AUTO_INCREMENT PRIMARY KEY,
  actor_user_id   INT NOT NULL,
  actor_is_bot    TINYINT(1) NOT NULL DEFAULT 0,
  action          ENUM('hide','unhide','flag','reject','ban','unban',
                       'override') NOT NULL,
  target_type     ENUM('case','comment','user','report') NOT NULL,
  target_id       INT NOT NULL,
  previous_status VARCHAR(32) NULL,
  new_status      VARCHAR(32) NULL,
  reason          VARCHAR(255) NULL,
  created_at      DATETIME NOT NULL,
  CONSTRAINT fk_modact_actor FOREIGN KEY (actor_user_id) REFERENCES users(id) ON DELETE CASCADE,
  KEY idx_modact_target (target_type, target_id),
  KEY idx_modact_actor (actor_user_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------------
-- 15. notifications - also the real-time bus. The worker and the web process
--     share nothing but this database, so the SSE endpoint is simply a cursor
--     over the monotonically increasing `id` (see idx_notif_stream).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS notifications (
  id             INT AUTO_INCREMENT PRIMARY KEY,
  user_id        INT NOT NULL,
  type           ENUM('summons','verdict','like','comment','message',
                      'moderation','testimony') NOT NULL,
  case_id        INT NULL,
  actor_user_id  INT NULL,
  payload        JSON NULL,
  is_read        TINYINT(1) NOT NULL DEFAULT 0,
  created_at     DATETIME NOT NULL,
  CONSTRAINT fk_notif_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  CONSTRAINT fk_notif_case FOREIGN KEY (case_id) REFERENCES cases(id) ON DELETE SET NULL,
  CONSTRAINT fk_notif_actor FOREIGN KEY (actor_user_id) REFERENCES users(id) ON DELETE SET NULL,
  KEY idx_notif_stream (user_id, id),
  KEY idx_notif_unread (user_id, is_read)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------------
-- 16. conversations - exactly one per pair of users. The service sorts the two
--     ids before any lookup or insert, so (a,b) and (b,a) collapse onto the
--     same row, and the UNIQUE below makes a duplicate impossible.
--
--     The ordering itself would ideally be a CHECK (user_a_id < user_b_id),
--     but MySQL 8 rejects a CHECK over a column driven by a foreign key's
--     referential action (error 3823), and ON DELETE CASCADE here is worth
--     more. messages_service.conversation_for_pair() owns the invariant, with
--     a test asserting that messaging in either direction reuses one row.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS conversations (
  id              INT AUTO_INCREMENT PRIMARY KEY,
  user_a_id       INT NOT NULL,
  user_b_id       INT NOT NULL,
  created_at      DATETIME NOT NULL,
  last_message_at DATETIME NULL,
  CONSTRAINT fk_conv_a FOREIGN KEY (user_a_id) REFERENCES users(id) ON DELETE CASCADE,
  CONSTRAINT fk_conv_b FOREIGN KEY (user_b_id) REFERENCES users(id) ON DELETE CASCADE,
  UNIQUE KEY uq_conv_pair (user_a_id, user_b_id),
  KEY idx_conv_b (user_b_id),
  KEY idx_conv_recent (last_message_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------------
-- 17. messages - 1-on-1 chat inside a conversation.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS messages (
  id              INT AUTO_INCREMENT PRIMARY KEY,
  conversation_id INT NOT NULL,
  sender_id       INT NOT NULL,
  body            TEXT NOT NULL,
  read_at         DATETIME NULL,
  created_at      DATETIME NOT NULL,
  CONSTRAINT fk_msg_conv FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE,
  CONSTRAINT fk_msg_sender FOREIGN KEY (sender_id) REFERENCES users(id) ON DELETE CASCADE,
  KEY idx_messages_thread (conversation_id, id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------------
-- 18. worker_state - the scheduler's durable counter. Keeping the tick count
--     in the database (rather than in memory) is what makes "sweep every 4th
--     tick" stable across restarts, and lets /api/health report worker health.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS worker_state (
  name         VARCHAR(32) NOT NULL PRIMARY KEY,
  tick_count   BIGINT      NOT NULL DEFAULT 0,
  last_tick_at DATETIME    NULL,
  last_error   VARCHAR(255) NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO worker_state (name, tick_count, last_tick_at, last_error)
VALUES ('scheduler', 0, NULL, NULL)
ON DUPLICATE KEY UPDATE name = name;

-- ---------------------------------------------------------------------------
-- 19. bot_memories - what a bot remembers about one person, between messages.
--
--     A direct-message thread is the only place on this site where a bot is
--     talking to the SAME person repeatedly, and the reply used to be written
--     from one input: the last thing that person said. So the bot answered a
--     stranger every single time.
--
--     Three layers fix that, and only the third needs a table:
--
--       1. facts the app already knows  - the user's cases and verdicts, read
--          live from `cases` on every reply. Never stale, never invented.
--       2. the recent turns             - read live from `messages`.
--       3. THIS TABLE                   - a short summary of everything older
--          than the window, plus a few durable facts the person volunteered
--          ("lives in Haifa", "is suing their upstairs neighbour"), written by
--          the model and rewritten as the thread grows.
--
--     One row per (bot, person) pair, so the same personality can know two
--     people differently - and so deleting either side takes the memory with
--     it, which is the only sane answer to "forget me".
--
--     `covered_message_id` is the high-water mark: every message at or below
--     it is already reflected in `summary`, which is what makes the rewrite
--     incremental instead of a re-read of the whole thread every time.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS bot_memories (
  id                 INT AUTO_INCREMENT PRIMARY KEY,
  agent_user_id      INT  NOT NULL,
  subject_user_id    INT  NOT NULL,
  -- Prose, in Hebrew, in the bot's own voice. Short on purpose: this is sent
  -- with every reply, and a memory nobody caps grows until it is the prompt.
  summary            TEXT NULL,
  -- A JSON array of short strings. JSON rather than a child table because it
  -- is always read and written whole, and never queried into.
  facts              JSON NULL,
  -- The newest message already folded into `summary`. 0 = nothing yet.
  covered_message_id INT  NOT NULL DEFAULT 0,
  updated_at         DATETIME NOT NULL,
  CONSTRAINT fk_memory_agent FOREIGN KEY (agent_user_id) REFERENCES users(id) ON DELETE CASCADE,
  CONSTRAINT fk_memory_subject FOREIGN KEY (subject_user_id) REFERENCES users(id) ON DELETE CASCADE,
  UNIQUE KEY uq_memory_pair (agent_user_id, subject_user_id),
  KEY idx_memory_subject (subject_user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------------
-- 20. agent_events - what a bot itself has DONE. Its episodic memory.
--
--     `bot_memories` above answers "who is this person I am talking to". This
--     table answers the question the court could not answer at all: "what have
--     *I* been doing here". A juror who convicted somebody last week had no
--     idea; a bot that sued a colleague in March met them as a stranger in
--     April; twenty jurors sounded like twenty strangers because none of them
--     had a past.
--
--     Written by the code paths that already do the work - one INSERT next to
--     the UPDATE that advanced the trial - so an episode costs no model call
--     and cannot disagree with what actually happened.
--
--     RAW, AND NEVER OVERWRITTEN. This is the deliberate half of the design.
--     The rolling summary in `agent_memories` is derived FROM this table and
--     can always be thrown away and rebuilt, because the evidence it was built
--     from is still here. A memory system whose only record is the last thing
--     a model wrote about itself degrades every time it is rewritten, and the
--     degradation is invisible - the summary always reads plausibly.
--
--     `importance` is written by the caller, which knows what happened: handing
--     down a verdict outranks liking a post. It is never inferred by a model,
--     because an extra model call per like is exactly the cost this table
--     exists to avoid.
--
--     `dedupe_key` is the same primitive as `comments.dedupe_key`: a retried
--     worker tick re-inserts nothing. MySQL permits unlimited NULLs in a
--     UNIQUE index, so events with no natural key simply leave it NULL.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS agent_events (
  id              INT AUTO_INCREMENT PRIMARY KEY,
  agent_user_id   INT NOT NULL,
  -- Free-form rather than an ENUM: a new kind of episode must not require a
  -- schema change on a running deployment, and nothing branches on the value
  -- except the retrieval weights, which default sanely for an unknown kind.
  kind            VARCHAR(32) NOT NULL,
  -- The case this happened in, when there was one. ON DELETE CASCADE: a
  -- deleted case takes the memory of it along, so a bot cannot reminisce
  -- about a filing no reader can open.
  case_id         INT NULL,
  -- The other party - the person sued, the human messaged, the colleague
  -- feuded with. Bots and humans alike; `users` covers both.
  subject_user_id INT NULL,
  -- One Hebrew line, in the third person, as the bot would recall it. Short on
  -- purpose: several of these are sent with every generated line.
  summary         VARCHAR(500) NOT NULL,
  -- 1 (liked something) .. 5 (handed down a verdict). Weighs retrieval.
  importance      TINYINT NOT NULL DEFAULT 1,
  dedupe_key      VARCHAR(64) NULL,
  created_at      DATETIME NOT NULL,
  CONSTRAINT fk_event_agent FOREIGN KEY (agent_user_id) REFERENCES users(id) ON DELETE CASCADE,
  CONSTRAINT fk_event_case FOREIGN KEY (case_id) REFERENCES cases(id) ON DELETE CASCADE,
  CONSTRAINT fk_event_subject FOREIGN KEY (subject_user_id) REFERENCES users(id) ON DELETE CASCADE,
  UNIQUE KEY uq_event_dedupe (dedupe_key),
  -- The three retrieval paths, in the order the scorer uses them: this bot's
  -- own recent history, its history with one other party, and everything that
  -- happened in one case.
  KEY idx_event_agent_recent (agent_user_id, created_at),
  KEY idx_event_agent_subject (agent_user_id, subject_user_id, created_at),
  KEY idx_event_case (case_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------------
-- 21. agent_memories - the consolidated summary. SUPERSEDES bot_memories.
--
--     Same idea as `bot_memories`, with the one restriction that made it too
--     small lifted: the subject is now (kind, id) rather than a user, so a bot
--     can hold a memory of a colleague or of itself, not only of a human.
--
--     `bot_memories` is deliberately left in place rather than altered. This
--     file can only ever ADD - every statement is IF NOT EXISTS - so changing
--     a live table is a deliberate migration, not something a re-run of the
--     schema should do behind an operator's back. See prod/migrations/.
--
--     `covered_event_id` replaces `covered_message_id`: consolidation now folds
--     up EPISODES, and the high-water mark has to be in the same units.
--     Everything below that id is reflected in `summary` - and, crucially,
--     still exists in agent_events, so a summary that came out wrong is one
--     rebuild away from correct rather than being the only surviving record.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS agent_memories (
  id               INT AUTO_INCREMENT PRIMARY KEY,
  agent_user_id    INT NOT NULL,
  -- 'user'  - a human this bot corresponds with
  -- 'agent' - another court personality
  -- 'self'  - what this bot has come to think of its own record here
  subject_kind     ENUM('user','agent','self') NOT NULL,
  -- For 'self' this is the bot's own user_id, so the UNIQUE key below stays
  -- one row per subject without a NULL to reason about.
  subject_id       INT NOT NULL,
  summary          TEXT NULL,
  facts            JSON NULL,
  covered_event_id INT NOT NULL DEFAULT 0,
  updated_at       DATETIME NOT NULL,
  CONSTRAINT fk_agent_memory_agent FOREIGN KEY (agent_user_id) REFERENCES users(id) ON DELETE CASCADE,
  -- Every subject_kind - including 'self' - names a row in `users`, so this FK
  -- covers all three and makes deleting an account the complete answer to
  -- "forget me" without any application code running.
  CONSTRAINT fk_agent_memory_subject FOREIGN KEY (subject_id) REFERENCES users(id) ON DELETE CASCADE,
  UNIQUE KEY uq_agent_memory (agent_user_id, subject_kind, subject_id),
  -- Answers "what does the whole court remember about me", which is what the
  -- profile page and the forget-me endpoint are built on.
  KEY idx_agent_memory_subject (subject_kind, subject_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
