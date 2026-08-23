"""Liveness and a window into the scheduler.

The worker runs in its own container, so "is the trial engine actually
advancing?" is not otherwise visible from the outside. Because the worker
records every tick in the database, this endpoint can answer it without any
cross-process channel.
"""

from __future__ import annotations

from flask import Blueprint, jsonify

from ..clock import now_utc
from ..config import get_settings
from ..db import connect

bp = Blueprint("health", __name__)


@bp.get("/health")
def health():
    settings = get_settings()
    body = {
        "status": "ok",
        "database": "down",
        "phase_minutes": settings.phase_minutes,
        "brain": "claude" if settings.use_claude else "offline",
        "worker": None,
        "server_time": now_utc().isoformat(timespec="seconds"),
    }

    db = None
    try:
        db = connect()
        db.query_value("SELECT 1")
        body["database"] = "up"
        state = db.query_one(
            "SELECT tick_count, last_tick_at, last_error FROM worker_state WHERE name = %s",
            ("scheduler",),
        )
        if state:
            last_tick = state["last_tick_at"]
            body["worker"] = {
                "tick_count": int(state["tick_count"]),
                "last_tick_at": last_tick.isoformat(timespec="seconds") if last_tick else None,
                "seconds_since_tick": (
                    round((now_utc() - last_tick).total_seconds(), 1) if last_tick else None
                ),
                "last_error": state["last_error"],
            }
    except Exception as exc:  # pragma: no cover - only when MySQL is unreachable
        body["status"] = "degraded"
        body["detail"] = str(exc)
    finally:
        if db is not None:
            db.close()

    return jsonify(body), 200 if body["status"] == "ok" else 503
