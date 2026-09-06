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


def test_geminis_quota_counts_only_todays_calls_against_the_cap(
    as_admin, log_call, backdate
):
    for _ in range(3):
        log_call(provider="gemini")
    yesterday = log_call(provider="gemini")
    backdate(yesterday, days=1)

    quota = as_admin.get("/api/admin/brain/usage").get_json()["gemini_quota"]

    assert quota == {"used": 3, "cap": 20, "remaining": 17}


def test_a_failed_gemini_call_still_spends_a_slot_in_the_quota(as_admin, log_call):
    """A rate-limited or malformed call still reached Google's API and still
    counted against the free tier there - hiding it here would make the quota
    look safer than it is."""
    log_call(provider="gemini", backend="offline", success=False, fallback_reason="boom")

    quota = as_admin.get("/api/admin/brain/usage").get_json()["gemini_quota"]

    assert quota["used"] == 1
