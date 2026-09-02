#!/usr/bin/env bash
# =============================================================================
#  deploy.sh - pull a published version and bring it live. Runs ON THE SERVER.
# =============================================================================
#      cd prod/ && ./deploy.sh v1.0.1      deploy that version
#      cd prod/ && ./deploy.sh             re-deploy whatever TAG is in .env
#      cd prod/ && ./deploy.sh --rollback  go back to the previous version
#
#  What it does, and why in this order:
#
#    1. Pull the new images FIRST, while the old ones keep serving traffic.
#       This is the slow step (tens of seconds on a small VPS) and it costs
#       zero downtime. Doing `up -d` without pulling first would stop the
#       containers and only then discover it has to download 250MB.
#    2. Only then recreate the containers - seconds, not minutes.
#    3. Verify /api/health actually answers before calling it a success.
#    4. If it does not, roll back to the version that was running, unprompted.
#
#  Step 4 is the reason this is a script and not three commands in a runbook.
#  A deploy that fails at 2am and leaves the site down until someone reads the
#  runbook is worse than one that quietly puts the old version back.
# =============================================================================
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
ENV_FILE="${ENV_FILE:-.env}"
HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-120}"

# Everything this script touches - the compose file, .env, .deploy-history - is
# in this folder, so cd here rather than to the repo root. That makes the script
# work identically whether you invoke it as ./deploy.sh from inside prod/ or as
# prod/deploy.sh from the repo root, and it is what lets the compose file's
# ../database/init.sql resolve correctly (Compose anchors relative paths to the
# compose file's directory, not to your shell's).
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

usage() {
  cat <<USAGE
${BOLD}Usage:${OFF} ./deploy.sh [version] [options]   ${DIM}(from the prod/ folder)${OFF}

  [version]          Version to deploy, e.g. v1.0.1. Omit to re-deploy the TAG
                     already in ${ENV_FILE} (useful after editing config).

${BOLD}Options:${OFF}
      --rollback     Redeploy the previous version, recorded in .deploy-history.
      --no-rollback  On health-check failure, leave the broken deploy up rather
                     than reverting. For when you would rather debug it live.
      --skip-health  Do not wait for /api/health. You are on your own.
  -h, --help         This text.

${BOLD}Environment:${OFF}
  COMPOSE_FILE       Default: docker-compose.yml (this folder's)
  HEALTH_TIMEOUT     Seconds to wait for a healthy stack. Default: 120
USAGE
}

TARGET_VERSION=""
DO_ROLLBACK=0
AUTO_ROLLBACK=1
SKIP_HEALTH=0

while [ $# -gt 0 ]; do
  case "$1" in
    --rollback)    DO_ROLLBACK=1; shift ;;
    --no-rollback) AUTO_ROLLBACK=0; shift ;;
    --skip-health) SKIP_HEALTH=1; shift ;;
    -h|--help)     usage; exit 0 ;;
    -*)            die "unknown option: $1  (--help for usage)" ;;
    *)
      [ -z "$TARGET_VERSION" ] || die "unexpected argument: $1"
      TARGET_VERSION="$1"; shift ;;
  esac
done

# --- preconditions ------------------------------------------------------------
[ -f "$COMPOSE_FILE" ] || die "$COMPOSE_FILE not found in $PROD_DIR - is this a complete checkout?"
[ -f "$ENV_FILE" ] || die "$ENV_FILE not found.
    Create it from the template and fill in the secrets:
      cp .env.example .env && chmod 600 .env && nano .env"

docker compose version >/dev/null 2>&1 || die "\`docker compose\` (v2) is required.
    The hyphenated docker-compose v1 is end-of-life and does not support the
    \`pull_policy\` and \`depends_on.condition\` keys this stack relies on."

# Read the tag currently in .env without sourcing the file - it contains
# passwords with characters the shell would happily interpret.
# tr strips quotes and any CR, so a .env edited on Windows does not yield a
# tag with an invisible carriage return glued to it - which pulls as a 404 and
# is genuinely hard to see in the error message.
current_tag() {
  sed -n 's/^[[:space:]]*TAG=\(.*\)$/\1/p' "$ENV_FILE" | tail -n1 | tr -d '\042\047 \r'
}

CURRENT_TAG="$(current_tag)"
HISTORY_FILE=".deploy-history"

# --- resolve what we are deploying --------------------------------------------
if [ "$DO_ROLLBACK" = 1 ]; then
  [ -n "$TARGET_VERSION" ] && die "--rollback takes no version argument"
  [ -f "$HISTORY_FILE" ] || die "no $HISTORY_FILE - nothing to roll back to.
    Deploy a known-good version explicitly instead:  ./deploy.sh v1.0.0"
  # Second-to-last line: the last line is what is running now.
  TARGET_VERSION="$(awk '{print $2}' "$HISTORY_FILE" | tail -n2 | head -n1)"
  [ -n "$TARGET_VERSION" ] || die "could not determine a previous version from $HISTORY_FILE"
  [ "$TARGET_VERSION" != "$CURRENT_TAG" ] || die "the previous version IS the current one ($CURRENT_TAG). Nothing to roll back to."
  warn "rolling back: $CURRENT_TAG -> $TARGET_VERSION"
fi

if [ -z "$TARGET_VERSION" ]; then
  TARGET_VERSION="$CURRENT_TAG"
  [ -n "$TARGET_VERSION" ] || die "no version given and no TAG= line in $ENV_FILE"
  info "no version given - re-deploying ${TARGET_VERSION} from $ENV_FILE"
fi

if [ "$TARGET_VERSION" = "latest" ]; then
  die "refusing to deploy 'latest'.
    A moving tag makes \`docker compose ps\` unable to tell you what is running
    and makes rollback impossible - the tag has already moved. Deploy a version."
fi

# --- write the new tag --------------------------------------------------------
# -i.bak then rm: GNU sed wants -i, BSD sed wants -i ''. Giving an explicit
# suffix is the one spelling both accept.
step "Deploying ${TARGET_VERSION}  ${DIM}(was ${CURRENT_TAG:-none})${OFF}"
if grep -q '^[[:space:]]*TAG=' "$ENV_FILE"; then
  sed -i.bak "s|^[[:space:]]*TAG=.*|TAG=${TARGET_VERSION}|" "$ENV_FILE" && rm -f "${ENV_FILE}.bak"
else
  printf '\nTAG=%s\n' "$TARGET_VERSION" >> "$ENV_FILE"
fi

# Restore the previous tag if we bail out anywhere below, so a failed deploy
# never leaves .env claiming a version that was never brought up.
restore_env_tag() {
  [ -n "$CURRENT_TAG" ] || return 0
  sed -i.bak "s|^[[:space:]]*TAG=.*|TAG=${CURRENT_TAG}|" "$ENV_FILE" && rm -f "${ENV_FILE}.bak"
}

# --- validate .env BEFORE touching anything -----------------------------------
# `docker compose pull` fails on a bad env file too - every secret in this
# compose file is `${VAR:?...}` - and its exit code looks identical to "the
# image does not exist" or "not logged in". Checking config here first means a
# missing CLIENT_ORIGIN is reported as exactly that, not misdiagnosed as a
# Docker Hub problem while nothing has actually been pulled yet.
CONFIG_ERR="$(docker compose -f "$COMPOSE_FILE" config -q 2>&1 1>/dev/null || true)"
if [ -n "$CONFIG_ERR" ]; then
  restore_env_tag
  die "$ENV_FILE is incomplete or invalid - nothing was pulled, nothing changed.

    $CONFIG_ERR

    Every required value is a blank line in $ENV_FILE waiting to be filled in:
      grep -E '^[A-Z_]+=$' $ENV_FILE"
fi

# --- pull ---------------------------------------------------------------------
# The whole minimal-downtime trick, in one command. The running containers are
# untouched while this downloads; only after it finishes does anything stop.
step "Pulling images  ${DIM}(the old version keeps serving during this)${OFF}"
# `set -e` treats `VAR=$(failing_command)` as a failing simple command and
# exits the SCRIPT right there, before the next line ever reads $? - silently
# skipping both the error message and restore_env_tag. set +e/-e around just
# this one command is what lets the failure be inspected instead of fatal.
set +e
PULL_ERR="$(docker compose -f "$COMPOSE_FILE" pull --quiet 2>&1 1>/dev/null)"
PULL_STATUS=$?
set -e
[ -n "$PULL_ERR" ] && printf '%s\n' "$PULL_ERR" >&2
if [ "$PULL_STATUS" -ne 0 ]; then
  restore_env_tag
  die "pull failed. ${TARGET_VERSION} may not exist on Docker Hub, or this host
    is not logged in for a private repository (\`docker login\`).
    Nothing was changed; the previous version is still running."
fi

# --- recreate -----------------------------------------------------------------
# Compose only recreates services whose image digest or config actually changed,
# so a frontend-only release does not restart the API. This is the
# several-seconds window.
#
# This step also BLOCKS on the one-shot seed job, which must exit 0 before
# server and worker start. If RDS is unreachable, app.seed's own wait_for_db
# retries for roughly six minutes before failing - so an `up` that seems hung
# is usually a wrong DB_HOST or a security group that does not allow this
# instance. `docker compose logs seed` says so on every attempt.
step "Starting containers  ${DIM}(waits for the seed job; minutes if RDS is unreachable)${OFF}"
if ! docker compose -f "$COMPOSE_FILE" up -d --remove-orphans; then
  warn "\`up\` failed"
  if [ "$AUTO_ROLLBACK" = 1 ] && [ -n "$CURRENT_TAG" ]; then
    warn "restoring ${CURRENT_TAG}"
    restore_env_tag
    docker compose -f "$COMPOSE_FILE" up -d --remove-orphans || true
  fi
  die "deploy failed during startup. Logs:
      docker compose -f $COMPOSE_FILE logs --tail=100"
fi

# --- verify -------------------------------------------------------------------
health_ok() {
  # Ask the API through nginx, from inside the web container - no curl needed on
  # the host, and it exercises the same path a browser takes, proxy included.
  docker compose -f "$COMPOSE_FILE" exec -T web \
    wget --quiet --output-document=- --timeout=5 http://127.0.0.1:8080/api/health 2>/dev/null \
    | grep -q '"status"'
}

if [ "$SKIP_HEALTH" = 1 ]; then
  warn "skipping the health check (--skip-health)"
else
  step "Waiting for the stack to report healthy  ${DIM}(up to ${HEALTH_TIMEOUT}s)${OFF}"
  deadline=$(( $(date +%s) + HEALTH_TIMEOUT ))
  healthy=0
  while [ "$(date +%s)" -lt "$deadline" ]; do
    if health_ok; then healthy=1; break; fi
    printf '.'
    sleep 3
  done
  printf '\n'

  if [ "$healthy" != 1 ]; then
    warn "${TARGET_VERSION} did not become healthy within ${HEALTH_TIMEOUT}s"
    docker compose -f "$COMPOSE_FILE" ps
    docker compose -f "$COMPOSE_FILE" logs --tail=40 server || true

    if [ "$AUTO_ROLLBACK" = 1 ] && [ -n "$CURRENT_TAG" ] && [ "$CURRENT_TAG" != "$TARGET_VERSION" ]; then
      step "Rolling back to ${CURRENT_TAG}"
      restore_env_tag
      docker compose -f "$COMPOSE_FILE" pull --quiet || true
      docker compose -f "$COMPOSE_FILE" up -d --remove-orphans || true
      die "deploy of ${TARGET_VERSION} failed its health check; ${CURRENT_TAG} has been restored.
    Investigate with:  docker compose -f $COMPOSE_FILE logs server"
    fi
    die "deploy of ${TARGET_VERSION} failed its health check and was left running (--no-rollback).
    Investigate with:  docker compose -f $COMPOSE_FILE logs -f server"
  fi
fi

# --- record -------------------------------------------------------------------
# Append-only, one line per deploy. This is what --rollback reads, and it is the
# cheapest possible answer to "when did this break, and what changed?".
printf '%s %s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$TARGET_VERSION" "${USER:-unknown}" >> "$HISTORY_FILE"

# --- clean up -----------------------------------------------------------------
# Untagged layers from superseded versions. Small VPS disks fill with these
# surprisingly fast. `image prune -f` without -a keeps every TAGGED image, so
# the previous version stays local and a rollback needs no download at all.
step "Pruning dangling images"
docker image prune -f >/dev/null 2>&1 || true

step "Deployed ${TARGET_VERSION}"
docker compose -f "$COMPOSE_FILE" ps --format 'table {{.Service}}\t{{.Status}}' 2>/dev/null || docker compose -f "$COMPOSE_FILE" ps
printf '\n    Roll back if needed:  %s./deploy.sh --rollback%s\n\n' "$BOLD" "$OFF"
