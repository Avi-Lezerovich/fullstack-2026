"""Aggregated view over `brain_calls`, for the ops dashboard's AI Usage tab.

`brain.LAST_CALL` answers "is the backend working right now"; this answers
"how much, how often does it fall back, and how close is Gemini to its free
tier" - which needs the persisted history, not one process's memory.
"""

from __future__ import annotations

from collections.abc import Sequence
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
    `credential_quotas` uses, so a provider's row here and the quota tiles
    above it are always talking about the same "today".
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


# One row is one provider ATTEMPT, not one brain call. When a credential is
# rate-limited and the next one answers, that is two rows - which is the honest
# unit, because it is the one that maps 1:1 to a request against somebody's
# quota. `calls` below therefore counts attempts.
_CREDENTIAL_COLUMNS = (
    "COALESCE(NULLIF(credential, ''), provider) AS credential, "
    "provider, "
    "COALESCE(NULLIF(model, ''), '-') AS model, "
    "COUNT(*) AS calls, "
    "SUM(success) AS successes, "
    "SUM(NOT success) AS failures, "
    "SUM(backend = 'offline' AND provider != 'offline') AS fallbacks, "
    "SUM(input_tokens) AS input_tokens, "
    "SUM(output_tokens) AS output_tokens, "
    "SUM(cache_read) AS cache_read, "
    "SUM(cache_write) AS cache_write, "
    "ROUND(AVG(NULLIF(latency_ms, 0))) AS avg_latency_ms "
)


def _shape_credential(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "credential": row["credential"],
            "provider": row["provider"],
            "model": row["model"],
            "calls": int(row["calls"]),
            "successes": int(row["successes"] or 0),
            "failures": int(row["failures"] or 0),
            "fallback_to_offline": int(row["fallbacks"] or 0),
            "input_tokens": int(row["input_tokens"] or 0),
            "output_tokens": int(row["output_tokens"] or 0),
            "cache_read": int(row["cache_read"] or 0),
            "cache_write": int(row["cache_write"] or 0),
            "avg_latency_ms": int(row["avg_latency_ms"] or 0),
        }
        for row in rows
    ]


def usage_by_credential(conn: Db | None = None, *, days: int = 0) -> list[dict[str, Any]]:
    """One row per (credential, model). `days=0` means today.

    Grouped by model as well as by key, because the same key can be pointed at
    a different model tomorrow and the two spends are not comparable - the free
    allowance differs by a factor of fifty between models of one provider.

    `COALESCE(NULLIF(credential, ''), provider)` is what lets history survive
    the migration: a row written before credentials existed has no label and
    appears under its provider name, rather than being dropped or charged to a
    key that never made the call.
    """
    window = (
        "created_at >= UTC_DATE()"
        if not days
        else f"created_at >= UTC_TIMESTAMP() - INTERVAL {int(days)} DAY"
    )
    with owned(conn) as db:
        rows = db.query_all(
            f"SELECT {_CREDENTIAL_COLUMNS} FROM brain_calls WHERE {window} "
            "GROUP BY 1, 2, 3 ORDER BY 1, 3"
        )
    return _shape_credential(rows)


def credential_quotas(
    credentials: Sequence[Any] | None = None, conn: Db | None = None
) -> list[dict[str, Any]]:
    """One tile per configured credential: what it has spent against its cap.

    Driven by the CHAIN rather than by the table, so a credential that has made
    no calls today still gets a tile - "api3-bedrock has done nothing" is a
    fact worth seeing, and a board built only from rows would omit exactly the
    credential somebody is wondering about.

    A cap of 0 means the allowance is unknown, which is honest for a paid
    account. It is reported as 0 rather than guessed at; the client renders
    that as "no cap set" instead of a bar that is either always full or always
    empty.

    Deliberately does NOT report the chain's in-memory cooldowns. Those belong
    to one process, the worker makes most of the calls, and a tile drawn from
    the API process's memory would be a confident statement about a machine it
    cannot see. `/api/health` is where "this process, right now" lives.
    """
    if credentials is None:
        credentials = get_settings().llm_chain

    with owned(conn) as db:
        spent = spend_today(db)

    out = []
    for credential in credentials:
        provider, model = _provider_and_model(credential)
        cap = credential.daily_cap or _default_cap(provider, model)
        used = spent.get(credential.label, 0)
        out.append(
            {
                "credential": credential.label,
                "provider": provider,
                "model": model,
                "used": used,
                "cap": cap,
                "remaining": max(0, cap - used) if cap else 0,
                "exhausted": bool(cap) and used >= cap,
            }
        )
    return out


def _provider_and_model(credential: Any) -> tuple[str, str]:
    """The credential's provider and the model it will actually ask for."""
    from ..brain import llm

    provider = llm.PROVIDERS.get(credential.provider)
    model = credential.model or (provider.default_model if provider else "")
    return credential.provider, model


def _default_cap(provider: str, model: str) -> int:
    """The published free-tier allowance, where there is one to publish."""
    return gemini_daily_cap(model) if provider == "gemini" else 0


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
