#!/usr/bin/env bash
# =============================================================================
#  init-rds.sh - apply database/init.sql to the RDS instance. Run ON THE EC2 BOX.
# =============================================================================
#      cd prod/ && ./init-rds.sh
#
#  Why this exists at all:
#
#  With a MySQL *container*, Docker's entrypoint applies init.sql automatically
#  from /docker-entrypoint-initdb.d - but only on an empty data volume. RDS has
#  no such hook. Nothing applies your schema. A fresh RDS instance is an empty
#  database, and the first thing the app does is fail against missing tables.
#
#  So this is the one manual step between creating the RDS instance and the
#  first deploy.
#
#  It is SAFE TO RE-RUN. All 18 CREATE TABLE statements in init.sql are
#  IF NOT EXISTS, so a second run adds nothing and drops nothing.
#
#  It is also, for the same reason, NOT A MIGRATION TOOL. IF NOT EXISTS can only
#  ever ADD a table; it will not add a column to a table that already exists or
#  change a type. Once you have real data, schema changes are deliberate SQL you
#  write and apply yourself - see prod/README.md, "Schema changes".
#
#  No mysql client is required on the instance: it borrows the one inside the
#  official mysql:8.0 image and throws the container away afterwards.
# =============================================================================
set -euo pipefail

ENV_FILE="${ENV_FILE:-.env}"
SCHEMA_FILE="${SCHEMA_FILE:-../database/init.sql}"
MYSQL_IMAGE="${MYSQL_IMAGE:-mysql:8.0}"

PROD_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROD_DIR"

if [ -t 1 ]; then
  BOLD=$'\033[1m'; RED=$'\033[31m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; DIM=$'\033[2m'; OFF=$'\033[0m'
else
  BOLD=""; RED=""; GREEN=""; YELLOW=""; DIM=""; OFF=""
fi
step() { printf '\n%s==>%s %s%s\n' "$BOLD$GREEN" "$OFF" "$BOLD" "$*$OFF"; }
info() { printf '    %s\n' "$*"; }
warn() { printf '%s warning:%s %s\n' "$YELLOW" "$OFF" "$*" >&2; }
die()  { printf '\n%serror:%s %s\n' "$RED" "$OFF" "$*" >&2; exit 1; }

case "${1:-}" in
  -h|--help)
    cat <<USAGE
${BOLD}Usage:${OFF} ./init-rds.sh [--check]   ${DIM}(from the prod/ folder, on the EC2 box)${OFF}

  Applies ../database/init.sql to the RDS instance named by DB_HOST in .env.
  Safe to re-run: every CREATE TABLE is IF NOT EXISTS.

  --check    Only test connectivity and list existing tables. Changes nothing.
USAGE
    exit 0 ;;
esac
CHECK_ONLY=0
[ "${1:-}" = "--check" ] && CHECK_ONLY=1

[ -f "$ENV_FILE" ]    || die "$ENV_FILE not found. Copy .env.example to .env and fill it in first."
[ -f "$SCHEMA_FILE" ] || die "$SCHEMA_FILE not found.
    This script needs the repo's database/init.sql, one level up from prod/.
    If you copied only prod/ onto the instance, copy database/init.sql too."

# Read one value out of .env WITHOUT sourcing the file - it holds passwords, and
# `source` would happily execute whatever punctuation they contain.
read_env() {
  sed -n "s/^[[:space:]]*$1=\(.*\)$/\1/p" "$ENV_FILE" | tail -n1 | tr -d '\042\047\r'
}

DB_HOST="$(read_env DB_HOST)"
DB_PORT="$(read_env DB_PORT)"; DB_PORT="${DB_PORT:-3306}"
DB_NAME="$(read_env DB_NAME)"
DB_USER="$(read_env DB_USER)"
DB_PASSWORD="$(read_env DB_PASSWORD)"

[ -n "$DB_HOST" ]     || die "DB_HOST is not set in $ENV_FILE (the RDS endpoint)"
[ -n "$DB_NAME" ]     || die "DB_NAME is not set in $ENV_FILE"
[ -n "$DB_USER" ]     || die "DB_USER is not set in $ENV_FILE"
[ -n "$DB_PASSWORD" ] || die "DB_PASSWORD is not set in $ENV_FILE"

case "$DB_HOST" in
  *:*)      die "DB_HOST must not include a port. Use DB_PORT for that.
    Got: $DB_HOST" ;;
  http*)    die "DB_HOST must be a bare hostname, not a URL.
    Got: $DB_HOST" ;;
  localhost|127.0.0.1)
    warn "DB_HOST is $DB_HOST - that is this instance, not RDS. Is that intended?" ;;
esac

step "Target"
info "host      ${DB_HOST}:${DB_PORT}"
info "database  ${DB_NAME}"
info "user      ${DB_USER}"

# MYSQL_PWD rather than -p on the command line: an argv password is visible in
# `ps` to every other process on the box for as long as the client runs.
run_mysql() {
  docker run --rm -i -e MYSQL_PWD="$DB_PASSWORD" "$MYSQL_IMAGE" \
    mysql --host="$DB_HOST" --port="$DB_PORT" --user="$DB_USER" \
          --connect-timeout=10 --default-character-set=utf8mb4 "$@"
}

step "Testing connectivity"
if ! run_mysql --database="$DB_NAME" --execute="SELECT 1" >/dev/null 2>/tmp/lolsuit-rds-err; then
  printf '%s\n' "$(cat /tmp/lolsuit-rds-err)" >&2
  rm -f /tmp/lolsuit-rds-err
  die "cannot reach the database.

    The three things that are almost always wrong, in order:

    1. ${BOLD}Security group.${OFF} The RDS instance's SG must allow inbound TCP
       ${DB_PORT} FROM THE EC2 INSTANCE'S SECURITY GROUP. Referencing the EC2 SG
       by id is correct; pasting an IP is fragile and breaks on restart.
    2. ${BOLD}The database does not exist.${OFF} init.sql contains no
       CREATE DATABASE - RDS creates it only if you set an initial database
       name. Create it once:
         docker run --rm -it -e MYSQL_PWD=... $MYSQL_IMAGE mysql -h $DB_HOST -u $DB_USER \\
           -e 'CREATE DATABASE IF NOT EXISTS \`$DB_NAME\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci'
    3. ${BOLD}Wrong credentials${OFF} in $ENV_FILE."
fi
rm -f /tmp/lolsuit-rds-err
info "connected"

EXISTING="$(run_mysql --database="$DB_NAME" --batch --skip-column-names \
  --execute="SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = '$DB_NAME'" 2>/dev/null || echo 0)"
info "tables currently present: ${EXISTING}"

if [ "$CHECK_ONLY" = 1 ]; then
  step "Existing tables"
  run_mysql --database="$DB_NAME" --execute="SHOW TABLES" || true
  info "--check: nothing was modified"
  exit 0
fi

if [ "${EXISTING:-0}" -gt 0 ]; then
  warn "this database already has ${EXISTING} tables."
  warn "init.sql is IF NOT EXISTS throughout, so re-running ADDS missing tables and"
  warn "changes nothing that already exists. It will NOT alter existing columns."
fi

step "Applying $SCHEMA_FILE"
run_mysql --database="$DB_NAME" < "$SCHEMA_FILE"
info "applied"

step "Result"
run_mysql --database="$DB_NAME" --execute="SHOW TABLES"

cat <<NEXT

  Schema is in place. Deploy the application:

    ./deploy.sh ${BOLD}v1.0.1${OFF}

  The seed job runs automatically on deploy and creates the 19 court bots and
  the demo accounts. It is idempotent, so it is safe on every deploy.

NEXT
