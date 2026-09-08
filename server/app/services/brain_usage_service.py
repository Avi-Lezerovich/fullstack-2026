"""Aggregated view over `brain_calls`, for the ops dashboard's AI Usage tab.

`brain.LAST_CALL` answers "is the backend working right now"; this answers
"how much, how often does it fall back, and how close is Gemini to its free
tier" - which needs the persisted history, not one process's memory.
"""

from __future__ import annotations

from typing import Any

from ..config import get_settings
from ..db import Db, owned

# Google's free-tier daily request allowance, per model. Not read from config
# because it is not ours to configure - it is Google's limit, and raising a
# setting here would not raise it there.
#
# Per MODEL, because that is the thing it actually varies with, and pinning it
# to the provider was a real bug rather than a simplification: the gauge read
# "20" while the configured model was a current-generation Flash whose
# allowance Google does not publish at all, and would have read "20" again
# after the default moved to a model allowed a thousand. A gauge that is wrong
# by fifty times is worse than no gauge, because it is believed.
#
# Prefix-matched, longest first, so a pinned point release inherits its
# family's number rather than falling through to the floor.
_GEMINI_FREE_TIER_BY_MODEL = {
    "gemini-2.5-flash-lite": 1000,
    "gemini-2.5-flash": 250,
    "gemini-3.5-flash-lite": 1000,
    "gemini-3-flash": 1500,
}

# What an unrecognised model is assumed to get. Deliberately the smallest
# number seen in the wild rather than an average: the failure mode of guessing
# high is spending a day's allowance before breakfast and not knowing why,
# which is the exact incident this constant exists because of.
GEMINI_UNKNOWN_MODEL_DAILY_CAP = 20


def gemini_daily_cap(model: str) -> int:
    """The free-tier allowance for `model`, or the cautious floor."""
    for known in sorted(_GEMINI_FREE_TIER_BY_MODEL, key=len, reverse=True):
        if model.startswith(known):
            return _GEMINI_FREE_TIER_BY_MODEL[known]
    return GEMINI_UNKNOWN_MODEL_DAILY_CAP


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


def spend_today(conn: Db | None = None) -> dict[str, int]:
    """Attempts per credential since UTC midnight - the chain's own counter.

    Keyed on the label rather than the provider, and skipping rows that have
    no label: a row written before credentials existed says nothing about
    which key spent it, and guessing would retire a live credential on the
    strength of history that is not its own.
    """
    with owned(conn) as db:
        rows = db.query_all(
            "SELECT credential, COUNT(*) AS calls FROM brain_calls "
            "WHERE created_at >= UTC_DATE() AND credential <> '' "
            "GROUP BY credential"
        )
    return {row["credential"]: int(row["calls"]) for row in rows}


def recent_failures(
    conn: Db | None = None, *, hours: int = 24, limit: int = 8
) -> list[dict[str, Any]]:
    """Why the backend has been falling back, most common first.

    `fallback_reason` has been written on every failed call since the table
    existed and has never been readable anywhere - so a deployment where every
    single call fails looks, on the dashboard, exactly like a deployment that
    is merely near its quota. This is the query that tells those two apart.

    Grouped on `LEFT(fallback_reason, 80)` rather than the whole string on
    purpose: several of the messages interpolate live numbers - the output
    budget and the thinking spend, in `llm.py`'s MAX_TOKENS branch - so
    grouping on the full text would return one row per call and hide exactly
    the "these 57 are all the same fault" shape this exists to show.
    """
    with owned(conn) as db:
        rows = db.query_all(
            "SELECT provider, LEFT(fallback_reason, 80) AS reason, "
            "COUNT(*) AS calls, MAX(created_at) AS last_seen "
            "FROM brain_calls "
            "WHERE success = 0 AND fallback_reason IS NOT NULL "
            "AND created_at >= UTC_TIMESTAMP() - INTERVAL %s HOUR "
            "GROUP BY provider, reason "
            "ORDER BY calls DESC, last_seen DESC "
            "LIMIT %s",
            (int(hours), int(limit)),
        )
    return [
        {
            "provider": row["provider"],
            "reason": row["reason"],
            "calls": int(row["calls"]),
            "last_seen": row["last_seen"].isoformat(timespec="seconds"),
        }
        for row in rows
    ]


def gemini_quota_today(conn: Db | None = None) -> dict[str, Any]:
    """Gemini's call count today against the configured model's free tier.

    Counts every attempt, successful or not - a call that failed still spent
    one of Google's requests, so a run of failures burning the quota is
    exactly the thing this exists to surface.

    The cap follows the configured model, and the model is reported alongside
    it so a reader can see which allowance they are being measured against
    rather than having to trust the bar.
    """
    from ..brain import llm

    settings = get_settings()
    model = settings.llm_model or llm.PROVIDERS["gemini"].default_model
    cap = gemini_daily_cap(model)
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
        "cap": cap,
        "model": model,
        "remaining": max(0, cap - used),
    }
