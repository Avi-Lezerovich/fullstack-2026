"""The tick loop.

Two layers of protection against doing the same work twice, and they are
deliberately independent:

**Correctness** lives in the services: every unit of work is claimed with
`FOR UPDATE SKIP LOCKED` and committed with a status-guarded UPDATE whose
rowcount is checked, backed by the unique `comments.dedupe_key` and
`jury_panels.case_id`. Two workers running flat out reach exactly the same
final state as one. This is the layer the tests assert against.

**Efficiency** is `GET_LOCK`, taken and released *inside* each tick and never
held across them. MySQL releases a named lock automatically when the holding
connection dies, so a `kill -9` needs no cleanup - no `locked_until` column, no
reaper, no clock-skew reasoning.
"""

from __future__ import annotations

import logging
import signal
import time
from typing import Any, Callable

from app.config import get_settings
from app.db import Db, connect, wait_for_db

from . import trial_tasks

log = logging.getLogger(__name__)

LOCK_NAME = "lolsuit:scheduler"
WORKER_NAME = "scheduler"


# --- the advisory lock ------------------------------------------------------


def acquire_lock(db: Db) -> bool:
    """Try to become the ticking worker. Zero timeout: never queue."""
    return bool(db.query_value("SELECT GET_LOCK(%s, 0)", (LOCK_NAME,), default=0))


def release_lock(db: Db) -> None:
    db.query_value("SELECT RELEASE_LOCK(%s)", (LOCK_NAME,))


# --- durable tick state -----------------------------------------------------


def bump_tick(db: Db) -> int:
    """Increment and return the tick counter.

    Committed before any work, and kept in the database rather than in memory,
    so "sweep every fourth tick" stays stable across restarts and is visible
    in /api/health.
    """
    db.execute(
        "UPDATE worker_state SET tick_count = tick_count + 1 WHERE name = %s", (WORKER_NAME,)
    )
    db.commit()
    return int(
        db.query_value("SELECT tick_count FROM worker_state WHERE name = %s", (WORKER_NAME,), default=0)
    )


def stamp_tick(db: Db, error: str | None = None) -> None:
    db.execute(
        "UPDATE worker_state SET last_tick_at = UTC_TIMESTAMP(), last_error = %s WHERE name = %s",
        (error, WORKER_NAME),
    )
    db.commit()


def safe(name: str, task: Callable[..., int], *args, **kwargs) -> int:
    """Run one task; log and swallow anything it throws.

    A single failing task must not abort the tick - the case that cannot
    advance should not stop six others from closing.
    """
    try:
        return task(*args, **kwargs)
    except Exception:
        log.exception("worker task %s failed", name)
        return 0


# --- the tick ---------------------------------------------------------------


def tick(conn: Db | None = None) -> dict[str, Any]:
    """One pass over everything that might be due. Returns a work summary.

    Ordering is deliberate: cheapest and most terminal first, so a slow batch
    of jurors never delays closing a case that has already finished.
    """
    own = conn is None
    db = conn if conn is not None else connect()

    try:
        number = bump_tick(db)
        summary: dict[str, Any] = {"tick": number}

        summary["filed_opened"] = safe("open_filed_cases", trial_tasks.open_filed_cases)
        summary["closed"] = safe("close_cases", trial_tasks.close_cases)
        summary["verdicts"] = safe("advance_verdicts", trial_tasks.advance_verdicts)
        summary["jurors_spoke"] = safe("run_due_jurors", trial_tasks.run_due_jurors)
        summary["juries_seated"] = safe("advance_witness_phase", trial_tasks.advance_witness_phase)

        # Moderation and idle bot activity are periodic rather than every-tick.
        for name, every, task in _periodic_tasks(number):
            summary[name] = safe(name, task) if every > 0 and number % every == 0 else 0

        stamp_tick(db)
        return summary
    finally:
        if own:
            db.close()


def _periodic_tasks(number: int) -> list[tuple[str, int, Callable[[], int]]]:
    """Tasks that run every Nth tick rather than every tick.

    The interval is read from configuration at tick time, so it can be changed
    without a restart.
    """
    settings = get_settings()
    tasks: list[tuple[str, int, Callable[[], int]]] = []

    from . import moderation_tasks, social_tasks

    tasks.append(("reports_worked", 1, moderation_tasks.work_report_queue))
    tasks.append(("swept", settings.sweep_every_ticks, moderation_tasks.sweep_unscanned))
    tasks.append(("arbitrated", settings.sweep_every_ticks, moderation_tasks.arbiter_pass))
    # The tick number seeds which action the chosen bot takes, so passing it
    # explicitly is what makes successive actions differ.
    tasks.append(
        (
            "bot_actions",
            settings.social_every_ticks,
            lambda: social_tasks.one_bot_social_action(number),
        )
    )
    # Answering a direct message is reactive, not initiative, so it is not
    # paced by `last_social_action_at` the way the feed activity is - a bot
    # that has just liked something should still answer you.
    tasks.append(("bot_replies", settings.social_every_ticks, social_tasks.reply_to_messages))

    return tasks


# --- the process ------------------------------------------------------------


class _Shutdown:  # pragma: no cover - signal plumbing
    """SIGTERM handling, so `docker compose down` stops the worker cleanly
    rather than killing it mid-transaction."""

    def __init__(self) -> None:
        self.requested = False
        signal.signal(signal.SIGTERM, self._handle)
        signal.signal(signal.SIGINT, self._handle)

    def _handle(self, *_args) -> None:
        log.info("shutdown requested; finishing the current tick")
        self.requested = True


def run_forever() -> None:  # pragma: no cover - the process entry point
    settings = get_settings()
    shutdown = _Shutdown()

    log.info(
        "scheduler starting: tick=%ss, phase=%s minutes per trial day",
        settings.tick_seconds,
        settings.phase_minutes,
    )

    # The database may still be starting up alongside us.
    wait_for_db().close()

    while not shutdown.requested:
        started = time.monotonic()
        db = None
        try:
            db = connect()
            if acquire_lock(db):
                try:
                    summary = tick(db)
                    if any(value for key, value in summary.items() if key != "tick"):
                        log.info("tick %s: %s", summary["tick"], summary)
                finally:
                    release_lock(db)
            else:
                log.debug("another worker holds the tick lock; skipping")
        except Exception as exc:
            log.exception("tick failed")
            try:
                if db is not None:
                    stamp_tick(db, error=str(exc)[:255])
            except Exception:
                log.exception("could not record the failure")
        finally:
            if db is not None:
                db.close()

        elapsed = time.monotonic() - started
        remaining = settings.tick_seconds - elapsed
        # Sleep in short slices so a SIGTERM is noticed promptly.
        while remaining > 0 and not shutdown.requested:
            time.sleep(min(1.0, remaining))
            remaining -= 1.0

    log.info("scheduler stopped")
