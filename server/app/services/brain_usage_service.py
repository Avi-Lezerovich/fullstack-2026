"""Aggregated view over `brain_calls`, for the ops dashboard's AI Usage tab.

`brain.LAST_CALL` answers "is the backend working right now"; this answers
"how much, how often does it fall back, and how close is Gemini to its free
tier" - which needs the persisted history, not one process's memory.
"""

from __future__ import annotations

from typing import Any

from ..db import Db, owned

# Gemini's free tier on the newest models: 20 requests/day. Not read from
# config because it is not ours to configure - it is Google's limit, and
# raising a setting here would not raise it there.
GEMINI_FREE_TIER_DAILY_CAP = 20


_USAGE_COLUMNS = (
    "provider, "
    "COUNT(*) AS calls, "
    "SUM(success) AS successes, "
    "SUM(NOT success) AS failures, "
    "SUM(backend = 'offline' AND provider != 'offline') AS fallbacks, "
    "SUM(input_tokens) AS input_tokens, "
    "SUM(output_tokens) AS output_tokens, "
    "SUM(cache_read) AS cache_read, "
    "SUM(cache_write) AS cache_write "
)


def _shape(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "provider": row["provider"],
            "calls": int(row["calls"]),
            "successes": int(row["successes"] or 0),
            "failures": int(row["failures"] or 0),
            "fallback_to_offline": int(row["fallbacks"] or 0),
            "input_tokens": int(row["input_tokens"] or 0),
            "output_tokens": int(row["output_tokens"] or 0),
            "cache_read": int(row["cache_read"] or 0),
            "cache_write": int(row["cache_write"] or 0),
        }
        for row in rows
    ]


def usage_today(conn: Db | None = None) -> list[dict[str, Any]]:
    """One row per provider, for calls made since the start of today (UTC).

    `UTC_DATE()`, not "the last 24 hours" - the same calendar boundary
    `gemini_quota_today` uses, so a provider's row here and the Gemini tile
    next to it are always talking about the same "today".
    """
    with owned(conn) as db:
        rows = db.query_all(
            f"SELECT {_USAGE_COLUMNS} FROM brain_calls "
            "WHERE created_at >= UTC_DATE() GROUP BY provider ORDER BY provider"
        )
    return _shape(rows)


def usage_this_week(conn: Db | None = None) -> list[dict[str, Any]]:
    """One row per provider, for a trailing 7-day window (not a calendar week)."""
    with owned(conn) as db:
        rows = db.query_all(
            f"SELECT {_USAGE_COLUMNS} FROM brain_calls "
            "WHERE created_at >= UTC_TIMESTAMP() - INTERVAL 7 DAY "
            "GROUP BY provider ORDER BY provider"
        )
    return _shape(rows)


def gemini_quota_today(conn: Db | None = None) -> dict[str, Any]:
    """Gemini's call count today against its 20/day free-tier cap.

    Counts every attempt, successful or not - a call that failed still spent
    one of Google's 20 requests, so a run of failures burning the quota is
    exactly the thing this exists to surface.
    """
    with owned(conn) as db:
        used = int(
            db.query_value(
                "SELECT COUNT(*) FROM brain_calls "
                "WHERE provider = 'gemini' AND created_at >= UTC_DATE()",
                default=0,
            )
        )
    return {
        "used": used,
        "cap": GEMINI_FREE_TIER_DAILY_CAP,
        "remaining": max(0, GEMINI_FREE_TIER_DAILY_CAP - used),
    }
