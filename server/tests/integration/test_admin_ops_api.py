# -*- coding: utf-8 -*-
"""The ops half of the admin dashboard: `/admin/overview` and
`/admin/brain/usage`.

Same permission split as `test_admin_api.py` covers for the moderation
endpoints - 401 anonymous, 403 signed-in-but-not-admin - checked here again
because `admin_ops.py` is its own blueprint with its own `require_admin`
decorators, not a shared one.
"""

from __future__ import annotations

import pytest

from app.services import brain_usage_service

pytestmark = pytest.mark.integration

ADMIN_OPS_ENDPOINTS = [
    ("get", "/api/admin/overview"),
    ("get", "/api/admin/brain/usage"),
]


@pytest.fixture
def as_admin(client, admin, signed_in):
    signed_in(admin)
    return client


@pytest.fixture
def log_call(db):
    """Insert one brain_calls row, dated now, and hand back its id.

    `created_at` is stamped by the app as UTC_TIMESTAMP() at insert time in
    production (see brain/__init__.py's `_log_call`); tests that need a row
    outside "today" or "this week" backdate it afterwards with `backdate`,
    the same way the rest of this suite ages a `created_at` it does not
    control directly - see e.g. test_moderation_service.py.
    """

    def _insert(
        *,
        task: str = "bot_comment",
        provider: str = "bedrock",
        backend: str = "llm",
        success: bool = True,
        fallback_reason: str | None = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cache_read: int = 0,
        cache_write: int = 0,
    ) -> int:
        result = db.execute(
            "INSERT INTO brain_calls "
            "(task, provider, backend, success, fallback_reason, "
            "input_tokens, output_tokens, cache_read, cache_write, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, UTC_TIMESTAMP())",
            (
                task,
                provider,
                backend,
                int(success),
                fallback_reason,
                input_tokens,
                output_tokens,
                cache_read,
                cache_write,
            ),
        )
        db.commit()
        return result.lastrowid

    return _insert


@pytest.fixture
def backdate(db):
    def _backdate(call_id: int, days: int) -> None:
        db.execute(
            "UPDATE brain_calls SET created_at = DATE_SUB(UTC_TIMESTAMP(), INTERVAL %s DAY) "
            "WHERE id = %s",
            (days, call_id),
        )
        db.commit()

    return _backdate


# --- who may open these endpoints -------------------------------------------


@pytest.mark.parametrize(("method", "path"), ADMIN_OPS_ENDPOINTS)
def test_every_endpoint_refuses_an_anonymous_request_with_401(client, method, path):
    response = getattr(client, method)(path)

    assert response.status_code == 401
    assert response.get_json()["code"] == "unauthorized"


@pytest.mark.parametrize(("method", "path"), ADMIN_OPS_ENDPOINTS)
def test_every_endpoint_refuses_an_ordinary_user_with_403(
    client, make_user, signed_in, method, path
):
    signed_in(make_user("עד רגיל", "witness@lolsuit.test"))

    response = getattr(client, method)(path)

    assert response.status_code == 403
    assert response.get_json()["code"] == "forbidden"


# --- the site overview -------------------------------------------------------


def test_the_overview_reuses_the_same_numbers_the_rest_of_the_dashboard_shows(
    as_admin, db, admin, make_user, make_case
):
    """Every count here has to agree with what its own dedicated view would
    show - a banned count that disagreed with the banned-users tab would be
    worse than not showing one at all.

    Asserted as deltas, not absolutes: the seeded cast already includes an
    admin and a handful of demo humans (see `seed_humans`), so "how many
    active users are there" is never zero going in.
    """
    before = as_admin.get("/api/admin/overview").get_json()

    human = make_user("אזרח", "citizen@lolsuit.test")
    make_user("מושעה", "banned@lolsuit.test", status="banned")
    make_user("בוט", "bot@lolsuit.test", is_bot=True)

    open_case = make_case(human["id"])
    closed_case = make_case(human["id"])
    db.execute("UPDATE cases SET status = 'closed' WHERE id = %s", (closed_case,))
    db.commit()

    from app.services import moderation_service as mod

    mod.report("case", open_case, human["id"], "abuse", conn=db)
    db.commit()

    after = as_admin.get("/api/admin/overview").get_json()

    # +1 human, not the banned account and not the bot.
    assert after["total_users"] - before["total_users"] == 1
    assert after["open_cases"] - before["open_cases"] == 1
    assert after["pending_reports"] - before["pending_reports"] == 1
    assert after["banned_users"] - before["banned_users"] == 1


def test_a_resolved_report_is_no_longer_pending(as_admin, db, admin, make_user, make_case):
    from app.services import moderation_service as mod

    author = make_user("תובע", "plaintiff@lolsuit.test")
    case = make_case(author["id"])
    _, report_id = mod.report("case", case, author["id"], "abuse", conn=db)
    db.commit()

    assert as_admin.get("/api/admin/overview").get_json()["pending_reports"] == 1

    mod.resolve_report(report_id, mod.RESOLVED_DISMISSED, resolver_id=admin["id"], conn=db)
    db.commit()

    assert as_admin.get("/api/admin/overview").get_json()["pending_reports"] == 0


# --- AI usage -----------------------------------------------------------------


def test_todays_calls_are_grouped_and_summed_by_provider(as_admin, log_call):
    log_call(provider="bedrock", backend="llm", success=True, input_tokens=100, output_tokens=40)
    log_call(provider="bedrock", backend="llm", success=True, input_tokens=50, output_tokens=20)
    log_call(
        provider="bedrock",
        backend="offline",
        success=False,
        fallback_reason="TimeoutError: took too long",
    )
    log_call(provider="offline", backend="offline", success=True)

    today = as_admin.get("/api/admin/brain/usage").get_json()["today"]
    by_provider = {row["provider"]: row for row in today}

    bedrock = by_provider["bedrock"]
    assert bedrock["calls"] == 3
    assert bedrock["successes"] == 2
    assert bedrock["failures"] == 1
    assert bedrock["fallback_to_offline"] == 1
    assert bedrock["input_tokens"] == 150
    assert bedrock["output_tokens"] == 60

    # Never configured at all: its own row, not folded into bedrock's and not
    # counted as a fallback - nothing was attempted to fall back from.
    assert by_provider["offline"]["calls"] == 1
    assert by_provider["offline"]["fallback_to_offline"] == 0


def test_a_call_from_last_week_counts_in_the_week_view_but_not_today(
    as_admin, log_call, backdate
):
    old = log_call(provider="bedrock")
    backdate(old, days=3)

    usage = as_admin.get("/api/admin/brain/usage").get_json()

    assert usage["today"] == []
    assert {row["provider"]: row["calls"] for row in usage["week"]} == {"bedrock": 1}


def test_a_call_from_over_a_week_ago_is_excluded_entirely(as_admin, log_call, backdate):
    ancient = log_call(provider="bedrock")
    backdate(ancient, days=10)

    usage = as_admin.get("/api/admin/brain/usage").get_json()

    assert usage["today"] == []
    assert usage["week"] == []


def test_a_quota_tile_counts_only_todays_calls(as_admin, db, backdate, monkeypatch):
    monkeypatch.setenv("LLM_CREDENTIALS", "provider=gemini,label=api1-gemini,key=k1,cap=1000")
    monkeypatch.setenv("BRAIN_FORCE_OFFLINE", "0")
    db.execute(
        "INSERT INTO brain_calls (task, provider, credential, model, backend, "
        "success, input_tokens, output_tokens, cache_read, cache_write, "
        "latency_ms, created_at) VALUES "
        "('t','gemini','api1-gemini','m','llm',1,0,0,0,0,0,UTC_TIMESTAMP()),"
        "('t','gemini','api1-gemini','m','llm',1,0,0,0,0,0,UTC_TIMESTAMP()),"
        "('t','gemini','api1-gemini','m','llm',1,0,0,0,0,0,UTC_TIMESTAMP()),"
        "('t','gemini','api1-gemini','m','llm',1,0,0,0,0,0,"
        "UTC_TIMESTAMP() - INTERVAL 1 DAY)"
    )
    db.commit()

    quota = as_admin.get("/api/admin/brain/usage").get_json()["credentials"][0]

    assert quota["used"] == 3
    assert quota["remaining"] == 997


def test_a_failed_call_still_spends_a_slot_in_the_quota(as_admin, db, monkeypatch):
    """A rate-limited or malformed call still reached Google's API and still
    counted against the free tier there - hiding it here would make the quota
    look safer than it is."""
    monkeypatch.setenv("LLM_CREDENTIALS", "provider=gemini,label=api1-gemini,key=k1,cap=1000")
    monkeypatch.setenv("BRAIN_FORCE_OFFLINE", "0")
    db.execute(
        "INSERT INTO brain_calls (task, provider, credential, model, backend, "
        "success, fallback_reason, input_tokens, output_tokens, cache_read, "
        "cache_write, latency_ms, created_at) VALUES "
        "('t','gemini','api1-gemini','m','offline',0,'boom',0,0,0,0,0,UTC_TIMESTAMP())"
    )
    db.commit()

    quota = as_admin.get("/api/admin/brain/usage").get_json()["credentials"][0]

    assert quota["used"] == 1


def test_the_published_allowance_is_looked_up_per_model(monkeypatch):
    """The cap is a property of the model, and the spread is enormous.

    One provider-wide number was wrong by fifty times the moment the model
    changed, and a gauge wrong by that much is worse than none because it
    gets believed.
    """
    from app.services.brain_usage_service import (
        GEMINI_UNKNOWN_MODEL_DAILY_CAP,
        gemini_daily_cap,
    )

    assert gemini_daily_cap("gemini-2.5-flash-lite") == 1000
    assert gemini_daily_cap("gemini-2.5-flash") == 250
    # A pinned point release inherits its family's number rather than falling
    # through to the floor.
    assert gemini_daily_cap("gemini-2.5-flash-lite-preview-09-2026") == 1000
    # Guessing high spends the day's allowance before anyone is awake.
    assert gemini_daily_cap("gemini-9.9-flash") == GEMINI_UNKNOWN_MODEL_DAILY_CAP


def test_failures_group_identical_reasons_into_one_row(as_admin, log_call):
    """57 calls failing the same way is one fact, not 57.

    The grouping is what makes the panel readable at all: an operator wants to
    see "everything is failing with THIS", and a list of 57 near-identical
    lines buries exactly that.
    """
    for _ in range(3):
        log_call(
            provider="gemini",
            backend="offline",
            success=False,
            fallback_reason="GeminiHttpError: gemini HTTP 404: model not found",
        )

    failures = as_admin.get("/api/admin/brain/usage").get_json()["failures"]

    assert len(failures) == 1
    assert failures[0]["calls"] == 3
    assert failures[0]["provider"] == "gemini"
    assert "404" in failures[0]["reason"]


def test_failures_ignore_successful_calls(as_admin, log_call):
    log_call(provider="gemini")

    assert as_admin.get("/api/admin/brain/usage").get_json()["failures"] == []


def test_failures_do_not_reach_back_beyond_the_window(as_admin, log_call, backdate):
    stale = log_call(
        provider="gemini",
        backend="offline",
        success=False,
        fallback_reason="GeminiHttpError: gemini HTTP 429: quota exhausted",
    )
    backdate(stale, days=2)

    assert as_admin.get("/api/admin/brain/usage").get_json()["failures"] == []


# --- the usage log actually reaches the database ------------------------------
#
# `_log_call` swallows every exception on purpose - a juror is mid-transaction
# when it runs, and an unlogged call beats a failed trial. The cost of that is
# that a schema drift makes the log silently stop rather than fail, and no test
# that only checks an endpoint's shape would ever notice. These two read the
# table back.


def test_a_logged_call_really_lands_in_the_table(db):
    """A row written through the real INSERT, against the real schema.

    This is the test that fails when migration 004 has not been applied, which
    is the whole reason it exists: every other test here inserts through a
    fixture that names its own columns, so all of them would keep passing
    against a table the application can no longer write to.
    """
    from app.brain import _log_call
    from app.brain.llm import Completion

    _log_call(
        "bot_comment",
        backend="llm",
        success=True,
        usage=Completion(
            text="x", input_tokens=11, output_tokens=22, credential="api1-gemini",
            model="gemini-2.5-flash-lite", latency_ms=345,
        ),
    )

    row = db.query_one(
        "SELECT credential, model, latency_ms, input_tokens FROM brain_calls "
        "ORDER BY id DESC LIMIT 1"
    )
    assert row["credential"] == "api1-gemini"
    assert row["model"] == "gemini-2.5-flash-lite"
    assert row["latency_ms"] == 345
    assert row["input_tokens"] == 11


def test_one_row_per_credential_attempted_not_one_per_call(db):
    """A 429'd credential spent a request, and the counter is a COUNT(*).

    Logging only the give-up would make three exhausted keys look like one
    failed call - wrong in the direction that costs money, because the cap
    that decides whether a key is spent counts exactly these rows.
    """
    from app.brain import _log_attempts
    from app.brain.llm import Attempt

    _log_attempts(
        "jury_deliberation",
        (
            Attempt("api1-gemini", "gemini", "m", ok=False, latency_ms=90, error="429"),
            Attempt("api2-gemini", "gemini", "m", ok=False, latency_ms=80, error="429"),
        ),
    )

    rows = db.query_all(
        "SELECT credential, backend, success FROM brain_calls "
        "WHERE task = 'jury_deliberation' ORDER BY id"
    )
    assert [r["credential"] for r in rows] == ["api1-gemini", "api2-gemini"]
    assert all(r["backend"] == "offline" and not r["success"] for r in rows)


def test_spend_today_counts_per_credential(db, log_call):
    """What the chain's cap is measured against."""
    from app.services.brain_usage_service import spend_today

    db.execute(
        "INSERT INTO brain_calls (task, provider, credential, model, backend, "
        "success, input_tokens, output_tokens, cache_read, cache_write, "
        "latency_ms, created_at) VALUES "
        "('t','gemini','api1-gemini','m','llm',1,0,0,0,0,0,UTC_TIMESTAMP()),"
        "('t','gemini','api1-gemini','m','llm',1,0,0,0,0,0,UTC_TIMESTAMP()),"
        "('t','gemini','api2-gemini','m','llm',1,0,0,0,0,0,UTC_TIMESTAMP())"
    )
    # A row from before credentials existed says nothing about which key spent
    # it, so it must not be attributed to one.
    log_call(provider="gemini")
    db.commit()

    assert spend_today(db) == {"api1-gemini": 2, "api2-gemini": 1}


# --- per-credential accounting ------------------------------------------------


def test_usage_is_grouped_by_credential_and_model(as_admin, db):
    db.execute(
        "INSERT INTO brain_calls (task, provider, credential, model, backend, "
        "success, input_tokens, output_tokens, cache_read, cache_write, "
        "latency_ms, created_at) VALUES "
        "('t','gemini','api1-gemini','gemini-2.5-flash-lite','llm',1,10,5,0,0,120,UTC_TIMESTAMP()),"
        "('t','gemini','api1-gemini','gemini-2.5-flash-lite','llm',1,10,5,0,0,180,UTC_TIMESTAMP()),"
        "('t','gemini','api2-gemini','gemini-2.5-flash-lite','offline',0,0,0,0,0,90,UTC_TIMESTAMP())"
    )
    db.commit()

    rows = as_admin.get("/api/admin/brain/usage").get_json()["by_credential"]
    by_label = {row["credential"]: row for row in rows}

    assert by_label["api1-gemini"]["calls"] == 2
    assert by_label["api1-gemini"]["input_tokens"] == 20
    assert by_label["api1-gemini"]["avg_latency_ms"] == 150
    assert by_label["api2-gemini"]["failures"] == 1


def test_a_row_from_before_credentials_reads_under_its_provider(as_admin, log_call):
    """History must survive the migration without being charged to a key."""
    log_call(provider="gemini")

    rows = as_admin.get("/api/admin/brain/usage").get_json()["by_credential"]

    assert [row["credential"] for row in rows] == ["gemini"]


def test_a_configured_credential_with_no_calls_still_gets_a_tile(as_admin, monkeypatch):
    """"api3-bedrock has done nothing today" is a fact worth seeing.

    A board built from the table alone would omit exactly the credential
    somebody is asking about.
    """
    monkeypatch.setenv(
        "LLM_CREDENTIALS",
        "provider=gemini,label=api1-gemini,key=k1,cap=1000;"
        "provider=bedrock,label=api3-bedrock,region=eu-central-1,cap=100",
    )
    monkeypatch.setenv("BRAIN_FORCE_OFFLINE", "0")

    quotas = as_admin.get("/api/admin/brain/usage").get_json()["credentials"]

    assert [q["credential"] for q in quotas] == ["api1-gemini", "api3-bedrock"]
    assert all(q["used"] == 0 for q in quotas)
    assert [q["cap"] for q in quotas] == [1000, 100]


def test_a_credential_cap_defaults_to_the_models_published_allowance(
    as_admin, monkeypatch
):
    """An operator who does not set `cap` still gets a real bar."""
    monkeypatch.setenv(
        "LLM_CREDENTIALS",
        "provider=gemini,label=api1-gemini,key=k1,model=gemini-2.5-flash-lite",
    )
    monkeypatch.setenv("BRAIN_FORCE_OFFLINE", "0")

    quota = as_admin.get("/api/admin/brain/usage").get_json()["credentials"][0]

    assert quota["cap"] == 1000
    assert quota["model"] == "gemini-2.5-flash-lite"


def test_an_exhausted_credential_is_marked_as_such(as_admin, db, monkeypatch):
    monkeypatch.setenv("LLM_CREDENTIALS", "provider=gemini,label=api1-gemini,key=k1,cap=2")
    monkeypatch.setenv("BRAIN_FORCE_OFFLINE", "0")
    db.execute(
        "INSERT INTO brain_calls (task, provider, credential, model, backend, "
        "success, input_tokens, output_tokens, cache_read, cache_write, "
        "latency_ms, created_at) VALUES "
        "('t','gemini','api1-gemini','m','llm',1,0,0,0,0,0,UTC_TIMESTAMP()),"
        "('t','gemini','api1-gemini','m','llm',1,0,0,0,0,0,UTC_TIMESTAMP())"
    )
    db.commit()

    quota = as_admin.get("/api/admin/brain/usage").get_json()["credentials"][0]

    assert quota == {
        "credential": "api1-gemini",
        "provider": "gemini",
        "model": "gemini-2.5-flash-lite",
        "used": 2,
        "cap": 2,
        "remaining": 0,
        "exhausted": True,
    }


def test_an_unknown_cap_is_reported_as_zero_rather_than_guessed(as_admin, monkeypatch):
    """Honest for a paid account, and the client renders it as "no cap set"
    rather than a bar that is always full or always empty."""
    monkeypatch.setenv(
        "LLM_CREDENTIALS", "provider=bedrock,label=api3-bedrock,region=eu-central-1"
    )
    monkeypatch.setenv("BRAIN_FORCE_OFFLINE", "0")

    quota = as_admin.get("/api/admin/brain/usage").get_json()["credentials"][0]

    assert quota["cap"] == 0
    assert quota["exhausted"] is False
