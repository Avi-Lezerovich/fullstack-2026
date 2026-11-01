-- ============================================================================
--  005-user-follows.sql - following people, for a deployment that already has
--  data.
-- ============================================================================
--  WHEN YOU NEED THIS
--
--  On a fresh database you do not: `database/init.sql` already contains the
--  CREATE TABLE statement, and `init-rds.sh` applies it.
--
--  You need it on any RDS instance initialised before user follows shipped.
--  Without the table the app starts as usual, then answers 500 on
--  `GET /api/cases/feed`, on every profile, and on the follow button.
--
--  HOW TO APPLY (take an RDS snapshot first - every time):
--
--      docker run --rm -i -e MYSQL_PWD="$DB_PASSWORD" mysql:8.0 \
--        mysql -h "$DB_HOST" -u "$DB_USER" "$DB_NAME" < 005-user-follows.sql
--
--  Safe to re-run: the CREATE is IF NOT EXISTS. Nothing is backfilled - nobody
--  follows anybody until they tap the button - and nothing existing is altered,
--  so rolling back is a redeploy of the previous image.
-- ============================================================================

SET NAMES utf8mb4;

-- The canonical definition lives in database/init.sql, section 25. Keep the
-- two in step.

CREATE TABLE IF NOT EXISTS user_follows (
  follower_id INT      NOT NULL,
  followee_id INT      NOT NULL,
  created_at  DATETIME NOT NULL,
  PRIMARY KEY (follower_id, followee_id),
  CONSTRAINT fk_user_follows_follower FOREIGN KEY (follower_id) REFERENCES users(id) ON DELETE CASCADE,
  CONSTRAINT fk_user_follows_followee FOREIGN KEY (followee_id) REFERENCES users(id) ON DELETE CASCADE,
  KEY idx_user_follows_followee (followee_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
