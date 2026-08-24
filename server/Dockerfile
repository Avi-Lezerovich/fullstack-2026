# =============================================================================
#  LolSuit API + worker image
# =============================================================================
#  Build context is server/ (NOT the repo root). Nothing in the running
#  application reads database/init.sql - the schema is applied by MySQL's own
#  entrypoint locally, and by a one-off client against RDS in production - so
#  the image has no reason to carry the repo root around.
#
#  One image, three processes: compose overrides the command to run gunicorn
#  (api), run_worker.py (worker) or `python -m app.seed` (seed). They share
#  every dependency, so building three images would only mean three caches to
#  invalidate.
# =============================================================================

# --- stage 1: dependencies ---------------------------------------------------
# Built into a virtualenv that the runtime stage copies wholesale. pip, its
# wheel cache and any transient build tooling stay behind in this stage.
FROM python:3.12-slim AS deps

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

# requirements.txt alone, before any source: this layer is the expensive one,
# and it must not be invalidated by an edit to a service module.
COPY requirements.txt /tmp/requirements.txt

RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt

# --- stage 2: runtime --------------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    PORT=5002

# A dedicated unprivileged account. --system because nobody logs in as it, and
# an explicit uid/gid so a bind-mounted file's ownership is predictable.
#
# The home directory is NOT optional despite nobody logging in: gunicorn's
# control server puts its socket under $HOME, and without a writable one every
# boot logs `Control server error: [Errno 13] Permission denied: '/home/lolsuit'`.
RUN groupadd --system --gid 1001 lolsuit \
 && useradd --system --uid 1001 --gid lolsuit --create-home --home-dir /home/lolsuit \
            --shell /usr/sbin/nologin lolsuit

COPY --from=deps /opt/venv /opt/venv

WORKDIR /app
# Ownership set during COPY rather than with a later `chown -R`, which would
# duplicate the whole tree into an extra layer.
COPY --chown=lolsuit:lolsuit . /app

USER lolsuit

EXPOSE 5002

# /api/health reports 503 (not 500) while MySQL is unreachable, which is exactly
# the semantics a healthcheck wants. urllib keeps this dependency-free - the
# slim base has no curl and adding one for a healthcheck is not worth ~4MB.
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
  CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('PORT', '5002') + '/api/health', timeout=4)"]

# gthread, not sync: an SSE notification stream holds its handler for minutes,
# and sync workers would each be blocked by a single subscriber. The timeout is
# comfortably above SSE_MAX_SECONDS' default so a healthy stream is never killed
# mid-flight.
#
# `sh -c` + `exec` so ${PORT} is expanded but gunicorn still becomes PID 1 and
# receives SIGTERM directly - otherwise `docker stop` would wait out the full
# grace period on every deploy.
CMD ["sh", "-c", "exec gunicorn \
  --worker-class gthread --workers ${GUNICORN_WORKERS:-2} --threads ${GUNICORN_THREADS:-16} \
  --timeout 600 --graceful-timeout 15 \
  --access-logfile - --error-logfile - \
  --bind 0.0.0.0:${PORT:-5002} run:app"]
