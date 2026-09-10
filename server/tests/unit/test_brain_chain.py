# -*- coding: utf-8 -*-
"""The credential chain: which key answers, and when one stops being asked.

The thing worth testing here is not "does it pick the first one". It is the
set of reasons a credential is skipped, because each of them is a different
production incident: a key that was never configured, a key that has spent its
allowance, a key that has just been told it is out, and a provider that cannot
do the task at all. Getting any of them wrong looks the same from outside -
the court quietly stops having personalities - which is precisely why they are
pinned here rather than left to be noticed.

Nothing here touches the network or the database; `spend_today` is patched.
"""

from __future__ import annotations

import pytest

from app.brain import chain, llm
from app.config import Credential

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _no_database(monkeypatch):
    """The chain reads its spend counts from MySQL. Here it reads a dict."""
    counts: dict[str, int] = {}
    monkeypatch.setattr(
        "app.services.brain_usage_service.spend_today", lambda *a, **k: dict(counts)
    )
    return counts


@pytest.fixture(autouse=True)
def _offline_is_off(monkeypatch):
    monkeypatch.setenv("BRAIN_FORCE_OFFLINE", "0")


def _configure(monkeypatch, *records: str) -> None:
    monkeypatch.setenv("LLM_CREDENTIALS", ";".join(records))


GEMINI_1 = "provider=gemini,label=api1-gemini,key=k1,model=gemini-2.5-flash-lite,cap=1000"
GEMINI_2 = "provider=gemini,label=api2-gemini,key=k2,model=gemini-2.5-flash-lite,cap=1000"
BEDROCK = "provider=bedrock,label=api3-bedrock,region=eu-central-1,cap=100"
GATEWAY = "provider=gateway,label=api4-gateway,key=k4,endpoint=https://x.invalid"


def _labels(**kwargs) -> list[str]:
    return [credential.label for credential, _, _ in chain.candidates(**kwargs)]


# --- order and eligibility ----------------------------------------------------


def test_the_chain_is_tried_in_the_order_it_was_written(monkeypatch):
    """Order is the operator's statement of preference, not an implementation
    detail: the cheapest or most generous key goes first, on purpose."""
    _configure(monkeypatch, GEMINI_1, GEMINI_2, BEDROCK)

    assert _labels() == ["api1-gemini", "api2-gemini", "api3-bedrock"]


def test_a_credential_missing_its_key_is_skipped_rather_than_tried(monkeypatch):
    """A chain whose second entry has no key is a chain of two, not a broken
    deployment. Trying it would spend a call to learn what is already known."""
    _configure(monkeypatch, GEMINI_1, "provider=gemini,label=api2-gemini,cap=1000")

    assert _labels() == ["api1-gemini"]


def test_a_credential_naming_an_unknown_provider_is_skipped(monkeypatch):
    _configure(monkeypatch, "provider=telepathy,label=api1-esp,key=k", GEMINI_1)

    assert _labels() == ["api1-gemini"]


def test_max_attempts_truncates_the_chain(monkeypatch):
    """A user-facing call cannot afford three 60-second timeouts in a row.

    Interactive tasks pass 2, and the point of the cap is latency rather than
    thrift - a person waiting three timeouts has been abandoned, not served.
    """
    _configure(monkeypatch, GEMINI_1, GEMINI_2, BEDROCK)

    assert _labels(max_attempts=chain.INTERACTIVE_MAX_ATTEMPTS) == [
        "api1-gemini",
        "api2-gemini",
    ]


# --- capability filtering -----------------------------------------------------


def test_a_gateway_credential_is_never_offered_a_structured_task(monkeypatch):
    """The gateway cannot enforce a schema, and a filing that is merely
    *suggested* a shape is the bug `Capabilities` was added to prevent."""
    _configure(monkeypatch, GATEWAY, GEMINI_1)

    assert _labels(structured=True) == ["api1-gemini"]
    assert _labels(structured=False) == ["api4-gateway", "api1-gemini"]


def test_capabilities_is_the_union_over_the_chain(monkeypatch):
    """One gateway entry anywhere must not disable every filing on the site.

    Reporting the first credential's answer would do exactly that, silently,
    and the symptom - bots that stop suing - looks nothing like the cause.
    """
    _configure(monkeypatch, GATEWAY, GEMINI_1)
    assert llm.capabilities().structured_output is True

    _configure(monkeypatch, GATEWAY)
    assert llm.capabilities().structured_output is False


# --- caps ---------------------------------------------------------------------


def test_a_credential_at_its_cap_is_passed_over(monkeypatch, _no_database):
    _configure(monkeypatch, "provider=gemini,label=api1-gemini,key=k1,cap=2", GEMINI_2)
    _no_database["api1-gemini"] = 2

    assert _labels() == ["api2-gemini"]


def test_calls_made_since_the_last_refresh_still_count(monkeypatch, _no_database):
    """The database is re-read once a minute; a worker tick fires faster.

    Eight jurors in four seconds would otherwise all read the same stale count
    and blow the cap by a full interval's worth of calls before noticing.
    """
    _configure(monkeypatch, "provider=gemini,label=api1-gemini,key=k1,cap=2", GEMINI_2)
    credential = Credential(label="api1-gemini", provider="gemini", api_key="k1", daily_cap=2)

    assert _labels()[0] == "api1-gemini"
    chain.note_attempt(credential)
    chain.note_attempt(credential)

    assert _labels() == ["api2-gemini"]


def test_a_credential_with_no_cap_is_never_blocked_by_one(monkeypatch, _no_database):
    """Zero means "allowance unknown", which is honest for a paid account and
    must not be read as "allowance of nothing"."""
    _configure(monkeypatch, "provider=gemini,label=api1-gemini,key=k1")
    _no_database["api1-gemini"] = 10_000

    assert _labels() == ["api1-gemini"]


# --- rpm pacing -----------------------------------------------------------


def test_rpm_is_parsed_from_llm_credentials(monkeypatch):
    from app.config import get_settings

    _configure(monkeypatch, "provider=gemini,label=api1-gemini,key=k1,rpm=12")

    assert get_settings().llm_credentials[0].rpm == 12


def test_rpm_defaults_to_zero_meaning_unpaced(monkeypatch):
    from app.config import get_settings

    _configure(monkeypatch, GEMINI_1)

    assert get_settings().llm_credentials[0].rpm == 0


def test_a_non_numeric_rpm_is_a_configuration_error(monkeypatch):
    from app.config import get_settings

    _configure(monkeypatch, "provider=gemini,label=api1-gemini,key=k1,rpm=soon")

    settings = get_settings()
    assert "rpm" in settings.llm_credential_errors[0]


def test_a_credential_at_its_rpm_is_skipped_in_favour_of_the_next(monkeypatch):
    """A burst that would blow the per-minute limit moves on rather than
    waiting - see the module docstring on why this is a skip, not a sleep."""
    _configure(monkeypatch, "provider=gemini,label=api1-gemini,key=k1,rpm=2", GEMINI_2)
    credential = Credential(label="api1-gemini", provider="gemini", api_key="k1", rpm=2)

    assert _labels()[0] == "api1-gemini"
    chain.note_attempt(credential)
    chain.note_attempt(credential)

    assert _labels() == ["api2-gemini"]


def test_a_credential_with_no_rpm_is_never_paced(monkeypatch):
    """Zero means unpaced, the same convention `daily_cap` uses."""
    _configure(monkeypatch, "provider=gemini,label=api1-gemini,key=k1")
    credential = Credential(label="api1-gemini", provider="gemini", api_key="k1")

    for _ in range(50):
        chain.note_attempt(credential)

    assert _labels() == ["api1-gemini"]


def test_the_rpm_window_rolls_over(monkeypatch):
    """A burst from a minute ago must not count against the next one."""
    _configure(monkeypatch, "provider=gemini,label=api1-gemini,key=k1,rpm=1")
    credential = Credential(label="api1-gemini", provider="gemini", api_key="k1", rpm=1)

    clock = [1_000.0]
    monkeypatch.setattr(chain.time, "monotonic", lambda: clock[0])

    chain.note_attempt(credential)
    assert _labels() == []

    clock[0] += 61
    assert _labels() == ["api1-gemini"]


def test_the_unavailable_line_names_the_rpm_reason(monkeypatch):
    _configure(monkeypatch, "provider=gemini,label=api1-gemini,key=k1,rpm=1")
    credential = Credential(label="api1-gemini", provider="gemini", api_key="k1", rpm=1)
    chain.note_attempt(credential)

    assert "api1-gemini 1/1 this minute" in chain.unavailable()


# --- what a failure does ------------------------------------------------------


def test_a_quota_error_retires_a_credential_for_the_rest_of_the_day(monkeypatch):
    """Not a short cooldown: the answer will be the same until the reset.

    This is also the branch that carries an uncapped key, whose real allowance
    Google does not publish - the common case on a free tier, not the odd one.
    """
    _configure(monkeypatch, "provider=gemini,label=api1-gemini,key=k1", GEMINI_2)
    credential = Credential(label="api1-gemini", provider="gemini", api_key="k1")

    chain.note_failure(credential, llm.GeminiHttpError(429, "RESOURCE_EXHAUSTED"))

    assert _labels() == ["api2-gemini"]
    assert chain.status()["api1-gemini"]["cooling_for"] > 3600


def test_an_ordinary_failure_rests_a_credential_only_briefly(monkeypatch):
    """A DNS blip must not pin the site to the last key in the chain."""
    _configure(monkeypatch, GEMINI_1, GEMINI_2)
    credential = Credential(label="api1-gemini", provider="gemini", api_key="k1")

    chain.note_failure(credential, TimeoutError("read timed out"))

    cooling = chain.status()["api1-gemini"]["cooling_for"]
    assert 0 < cooling <= chain._TRANSIENT_COOLDOWN_SECONDS


def test_a_success_clears_an_earlier_cooldown(monkeypatch):
    _configure(monkeypatch, GEMINI_1)
    credential = Credential(label="api1-gemini", provider="gemini", api_key="k1")

    chain.note_failure(credential, TimeoutError("blip"))
    assert _labels() == []

    chain.note_success(credential)
    assert _labels() == ["api1-gemini"]


@pytest.mark.parametrize(
    "exc",
    [
        llm.GeminiHttpError(429, "gemini HTTP 429: RESOURCE_EXHAUSTED quota"),
        Exception("RESOURCE_EXHAUSTED: generate_content_free_tier_requests"),
        Exception("ThrottlingException: Too many requests"),
        Exception("rate limit exceeded"),
    ],
)
def test_every_shape_a_quota_answer_arrives_in_is_recognised(exc):
    """Codes where there is one, prose where there is not.

    The SDK providers raise types this module deliberately does not import -
    the packages are optional - so their half has to be matched on text.
    """
    assert chain.is_quota_error(exc)


@pytest.mark.parametrize(
    "exc",
    [ValueError("empty completion"), TimeoutError("read timed out"), KeyError("model")],
)
def test_an_ordinary_failure_is_not_mistaken_for_a_quota_answer(exc):
    """Over-matching here writes off a healthy key for a day."""
    assert not chain.is_quota_error(exc)


# --- a rate 429 is not a quota 429 ---------------------------------------


@pytest.mark.parametrize(
    "exc",
    [
        llm.GeminiHttpError(
            429,
            "gemini HTTP 429: RESOURCE_EXHAUSTED quota_id: "
            "GenerateRequestsPerMinutePerProjectPerModel-FreeTier",
        ),
        Exception("ThrottlingException: Too many requests"),
        Exception("rate limit exceeded"),
        Exception("TooManyRequestsException: slow down"),
    ],
)
def test_a_burst_is_recognised_as_a_rate_limit(exc):
    """Too fast, not out for the day - see the module docstring."""
    assert chain.is_rate_limit_error(exc)


@pytest.mark.parametrize(
    "exc",
    [
        llm.GeminiHttpError(429, "gemini HTTP 429: RESOURCE_EXHAUSTED"),
        Exception("RESOURCE_EXHAUSTED: generate_content_free_tier_requests"),
        ValueError("empty completion"),
    ],
)
def test_a_plain_day_quota_is_not_mistaken_for_a_rate_limit(exc):
    """No 'PerMinute' in the quota id - and Google's daily allowance running
    out looks exactly like this - so the long cooldown must still apply."""
    assert not chain.is_rate_limit_error(exc)


def test_a_rate_limit_rests_a_credential_only_for_the_window(monkeypatch):
    _configure(monkeypatch, GEMINI_1, GEMINI_2)
    credential = Credential(label="api1-gemini", provider="gemini", api_key="k1")

    chain.note_failure(
        credential,
        llm.GeminiHttpError(
            429,
            "gemini HTTP 429: RESOURCE_EXHAUSTED quota_id: "
            "GenerateRequestsPerMinutePerProjectPerModel-FreeTier",
        ),
    )

    cooling = chain.status()["api1-gemini"]["cooling_for"]
    assert 0 < cooling <= chain._RATE_COOLDOWN_SECONDS
    assert _labels() == ["api2-gemini"]


def test_an_aws_throttle_rests_a_credential_only_briefly_not_until_midnight(monkeypatch):
    """AWS has no daily-quota concept behind a throttling exception - it is
    always a request-rate answer, never 'you are out until tomorrow'."""
    _configure(monkeypatch, "provider=bedrock,label=api3-bedrock,region=eu-central-1")
    credential = Credential(label="api3-bedrock", provider="bedrock", aws_region="eu-central-1")

    chain.note_failure(credential, Exception("ThrottlingException: Too many requests"))

    assert chain.status()["api3-bedrock"]["cooling_for"] <= chain._RATE_COOLDOWN_SECONDS


# --- when there is nothing left ----------------------------------------------


def test_the_unavailable_line_says_what_happened_to_each_credential(monkeypatch):
    """The single most useful sentence a health endpoint carries on a bad day."""
    _configure(monkeypatch, "provider=gemini,label=api1-gemini,key=k1,cap=1", GEMINI_2)
    chain.note_failure(
        Credential(label="api2-gemini", provider="gemini", api_key="k2"),
        llm.GeminiHttpError(429, "gemini HTTP 429: RESOURCE_EXHAUSTED quota"),
    )
    chain.note_attempt(Credential(label="api1-gemini", provider="gemini", api_key="k1"))

    line = chain.unavailable()

    assert "api1-gemini 1/1" in line
    assert "api2-gemini cooling" in line


def test_forcing_offline_empties_the_chain(monkeypatch):
    """BRAIN_FORCE_OFFLINE is a stop, and it has to stop this too."""
    _configure(monkeypatch, GEMINI_1)
    monkeypatch.setenv("BRAIN_FORCE_OFFLINE", "1")

    assert _labels() == []
    assert chain.unavailable() == "no credentials configured"


# --- failover, end to end through llm._try_chain ------------------------------


def _provider(*, fails=None, text="שלום"):
    """A provider that either raises or answers, recording what it was given."""
    seen: list[str] = []

    def complete(system, messages, *, credential, model, **kwargs):
        seen.append(credential.label)
        if fails and credential.label in fails:
            raise fails[credential.label]
        return llm.Completion(text=text)

    return complete, seen


def _install(monkeypatch, complete):
    monkeypatch.setattr(
        llm,
        "PROVIDERS",
        {
            **llm.PROVIDERS,
            "gemini": llm.Provider(
                complete=complete,
                is_configured=lambda credential: bool(credential.api_key),
                default_model="gemini-2.5-flash-lite",
                capabilities=llm.SDK_CAPABILITIES,
            ),
        },
    )


def test_the_next_credential_answers_when_the_first_one_cannot(monkeypatch):
    _configure(monkeypatch, GEMINI_1, GEMINI_2)
    complete, seen = _provider(fails={"api1-gemini": llm.GeminiHttpError(429, "gemini HTTP 429: RESOURCE_EXHAUSTED quota")})
    _install(monkeypatch, complete)

    completion = llm._try_chain(
        lambda provider, credential, model: provider.complete(
            [], [], credential=credential, model=model
        )
    )

    assert seen == ["api1-gemini", "api2-gemini"]
    assert completion.credential == "api2-gemini"
    assert completion.model == "gemini-2.5-flash-lite"


def test_the_winner_is_stamped_with_what_produced_it(monkeypatch):
    """`brain` persists provenance from this, and the providers never see it.

    Stamping in the chain rather than in each provider is what keeps "adding a
    provider" a single entry in PROVIDERS.
    """
    _configure(monkeypatch, GEMINI_1)
    complete, _ = _provider()
    _install(monkeypatch, complete)

    completion = llm._try_chain(
        lambda provider, credential, model: provider.complete(
            [], [], credential=credential, model=model
        )
    )

    assert completion.credential == "api1-gemini"
    assert completion.latency_ms >= 0


def test_a_credential_is_never_asked_twice_within_one_call(monkeypatch):
    """Retrying the same key spends a second request to learn the same thing.

    Within-provider retries belong to `_gemini_post`, and only for the
    statuses that mean "busy" rather than "no".
    """
    _configure(monkeypatch, GEMINI_1)
    complete, seen = _provider(fails={"api1-gemini": ValueError("nope")})
    _install(monkeypatch, complete)

    with pytest.raises(llm.AllCredentialsFailed):
        llm._try_chain(
            lambda provider, credential, model: provider.complete(
                [], [], credential=credential, model=model
            )
        )

    assert seen == ["api1-gemini"]


def test_every_attempt_is_carried_on_the_exception(monkeypatch):
    """`brain` writes one usage row per attempt, and gets them from here.

    A summary row would make two exhausted keys look like one failed call -
    wrong in the direction that costs money, since the cap that decides
    whether a key is spent is a COUNT(*) over exactly those rows.
    """
    _configure(monkeypatch, GEMINI_1, GEMINI_2)
    complete, _ = _provider(
        fails={
            "api1-gemini": llm.GeminiHttpError(429, "gemini HTTP 429: RESOURCE_EXHAUSTED quota"),
            "api2-gemini": llm.GeminiHttpError(429, "gemini HTTP 429: RESOURCE_EXHAUSTED quota"),
        }
    )
    _install(monkeypatch, complete)

    with pytest.raises(llm.AllCredentialsFailed) as caught:
        llm._try_chain(
            lambda provider, credential, model: provider.complete(
                [], [], credential=credential, model=model
            )
        )

    attempts = caught.value.attempts
    assert [a.credential for a in attempts] == ["api1-gemini", "api2-gemini"]
    assert all(not a.ok and "429" in a.error for a in attempts)


def test_an_exhausted_chain_says_so_rather_than_raising_something_shapeless(
    monkeypatch,
):
    """With nothing left to try there are no attempts to report, so the
    message has to carry the state instead - which is what an operator reads
    on /api/health when the court has gone quiet."""
    _configure(monkeypatch, "provider=gemini,label=api1-gemini,key=k1,cap=1")
    complete, _ = _provider()
    _install(monkeypatch, complete)
    chain.note_attempt(Credential(label="api1-gemini", provider="gemini", api_key="k1"))

    with pytest.raises(llm.AllCredentialsFailed, match="api1-gemini 1/1") as caught:
        llm._try_chain(
            lambda provider, credential, model: provider.complete(
                [], [], credential=credential, model=model
            )
        )

    assert caught.value.attempts == ()
