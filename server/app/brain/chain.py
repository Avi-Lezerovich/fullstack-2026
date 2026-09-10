"""Which credential answers, and what happens when it stops answering.

`llm.py` knows how to talk to one provider with one key. This knows which key
to hand it, in what order, and when to stop asking one that has said no.

--- three things this is deliberately not ------------------------------------

**Not a lock.** The daily cap is a budget kept per process. Gunicorn runs
several workers and the scheduler is a fourth process, each with its own copy,
so the true aggregate can overshoot a cap by roughly (processes x calls per
refresh interval). Making it exact would mean serialising every model call
behind one row in MySQL - `GET_LOCK` or `SELECT ... FOR UPDATE` - which trades
the whole site's throughput for a number that the 429 handler below already
covers properly. The cap is what keeps a well-behaved deployment inside its
allowance; the 429 is what handles being wrong about the allowance.

**Not a retry.** A credential is tried at most once per call. Retrying the
same key is `_gemini_post`'s job and happens for the statuses that mean
"busy"; retrying it here would mean re-spending a quota to learn the same
thing twice.

**Not a health check.** `usable()` in `llm.py` is local and free - does this
credential name a provider, and does it have the key that provider needs. It
never touches the network. Whether the key is *valid* is discovered by using
it, which is exactly what `note_failure` is for.

--- why the counts come from the database ------------------------------------

There is no Redis here and this does not need one. `brain_calls` already gets
one row per attempt for entirely separate reasons - it is the usage history the
admin board reads - so the count of what a credential has spent today is a
query against a table that is already being written. The refresh is throttled
to once a minute and a local delta covers the interval, because a worker tick
that fires eight jurors in four seconds would otherwise blow a cap by a full
interval's worth of calls before noticing.

Double-counting across a refresh boundary is possible and tolerated: it
retires a credential slightly early. That is the safe direction. Under-counting
spends somebody's quota and finds out from Google.

--- the daily cap is a budget, and so is the RPM limit -----------------------

`daily_cap` (above) is deliberately not a lock, for the reasons above. `rpm`
is the same philosophy applied to a one-minute window instead of a one-day
one, because a free-tier quota is usually two numbers, not one: Google
publishes a per-day allowance AND a per-minute one, and a worker tick that
fires several jurors in a handful of seconds can blow the per-minute number
while the day's allowance still has thousands of calls left in it. Checked in
`candidates()` exactly like `daily_cap` - a credential that has already been
tried `rpm` times in the trailing 60 seconds is skipped in favour of the next
one in the chain, never blocked on - see "not a retry" and "not a lock" above;
sleeping inside this lock to wait out a window would be exactly the kind of
serialisation this module exists to avoid, and a worker's next tick (15
seconds by default) is already a shorter wait than the 60-second window would
require anyway. Zero means unpaced, same convention as `daily_cap`.

This is preventive - it keeps a well-paced deployment from bursting past its
own configured limit. `is_rate_limit_error` below is the reactive half, for
when a burst happens anyway (an unconfigured `rpm`, or one set too high): it
tells a per-minute 429 apart from a per-day one, because a credential written
off until UTC midnight over a burst that clears in under a minute has lost
nearly a full day's real allowance for no reason.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from ..config import Credential, get_settings

# `llm` is imported inside the methods that need it, not here. This module sits
# ABOVE it - llm.generate() asks the chain which credential to use - so a
# module-scope import would close a cycle whose behaviour depends on which of
# the two happened to be imported first.

log = logging.getLogger(__name__)

# How long a cached spend count is trusted before it is re-read. One minute is
# short enough that a second process's spending shows up while a cap still
# means something, and long enough that the query is noise next to the model
# call it is guarding.
_SPEND_TTL_SECONDS = 60.0

# How long a credential is rested after a failure that is NOT a quota answer -
# a timeout, a DNS blip, a 500. Long enough that a flapping provider does not
# get asked on every tick, short enough that a five-minute outage does not
# pin the whole site to the last credential in the chain for an hour.
_TRANSIENT_COOLDOWN_SECONDS = 120.0

# How many credentials one call may work through. Three is the whole chain for
# a typical deployment; interactive callers pass 2, because the timeout is 60
# seconds and a user waiting three of those has been abandoned, not served.
DEFAULT_MAX_ATTEMPTS = 3
INTERACTIVE_MAX_ATTEMPTS = 2

# The window a credential's `rpm` is measured over. Fixed at one minute
# because that is the unit every provider publishes a per-minute figure in;
# there is no per-deployment reason to make it configurable.
_RPM_WINDOW_SECONDS = 60.0

# What a provider says when it is out of quota, in the two forms it arrives in:
# a status code where we have one, and prose where we do not. The codes are the
# reliable half - `GeminiHttpError` carries `.code` precisely so this does not
# have to guess - and the strings cover the SDK providers, whose exception
# types are not imported here on purpose (the packages are optional).
_QUOTA_STATUS = frozenset({429})
_QUOTA_MARKERS = (
    "resource_exhausted",
    "quota",
    "rate limit",
    "rate_limit",
    "too many requests",
    "throttlingexception",
    "toomanyrequestsexception",
)


def is_quota_error(exc: BaseException) -> bool:
    """Whether this failure means "you have had your share for now"."""
    if getattr(exc, "code", None) in _QUOTA_STATUS:
        return True
    if getattr(getattr(exc, "response", None), "status_code", None) in _QUOTA_STATUS:
        return True
    text = f"{type(exc).__name__}: {exc}".lower()
    return any(marker in text for marker in _QUOTA_MARKERS)


# The subset of `is_quota_error` that means "you were too fast", not "you are
# out for today". AWS's throttling exceptions are inherently about a request
# RATE (calls per second/minute) - there is no AWS analogue of Google's daily
# free-tier cap behind them - so they belong here rather than in the day-long
# branch. Google's own 429 is ambiguous by status code and by the generic
# "quota"/"resource_exhausted" words alike, since both a daily cap and a
# per-minute cap raise the identical shape; the one reliable per-minute signal
# is the quota id itself, which Google spells with "PerMinute"
# (`GenerateRequestsPerMinutePerProjectPerModel-FreeTier`, see docs/brain.md).
# Absent that marker, a Google quota error keeps the conservative day-long
# treatment - the existing behaviour - rather than guessing short.
_RATE_MARKERS = (
    "throttlingexception",
    "toomanyrequestsexception",
    "rate limit",
    "rate_limit",
    "too many requests",
    "perminute",
)

# One RPM window. A burst against a per-minute limit clears once the window
# rolls over, so there is no reason to hold a key back any longer than that -
# unlike a day quota, which really does mean "not until tomorrow".
_RATE_COOLDOWN_SECONDS = 60.0


def is_rate_limit_error(exc: BaseException) -> bool:
    """Whether this 429 means "too fast", as opposed to "out for the day".

    A strict subset of `is_quota_error`: every rate-limit failure is also
    quota-shaped (both arrive as a 429 with nothing to retry immediately), but
    not every quota failure is a rate limit - most of them, on this site's
    free-tier keys, are the daily allowance running out, and that one still
    needs the long cooldown.
    """
    text = f"{type(exc).__name__}: {exc}".lower()
    return any(marker in text for marker in _RATE_MARKERS)


def _next_utc_midnight() -> float:
    """Monotonic deadline at the next UTC day boundary.

    Google's daily quotas reset at midnight Pacific and everything here counts
    in UTC, so this is approximate by up to eight hours - deliberately, and in
    the safe direction: a credential written off until UTC midnight is rested
    at least as long as it needs to be, never less. Getting it exactly right
    would mean tracking each provider's own reset zone to save a few calls on
    a key that has already proved it is empty.
    """
    now = datetime.now(timezone.utc)
    midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return time.monotonic() + (midnight - now).total_seconds()


@dataclass
class _State:
    """One credential's story since this process started."""

    spent: int = 0  # every process's attempts today, as of the last refresh
    local: int = 0  # this process's attempts today, counted as they happen
    cooldown_until: float = 0.0  # monotonic; 0 means available
    # Monotonic timestamps of recent attempts, oldest first, pruned to the
    # trailing RPM window. Only populated for a credential whose `rpm` is set -
    # see `note_attempt` - so an unpaced credential carries no bookkeeping for
    # a limit it does not have.
    recent_calls: deque[float] = field(default_factory=deque)

    @property
    def used(self) -> int:
        """The best estimate of what this credential has spent today.

        The larger of the two counters, not their sum. `spent` already
        includes this process's own rows once they have been written, so
        adding them would double-count everything older than one refresh;
        taking the max keeps the shared figure when it is ahead and this
        process's own when the database has not caught up yet - which is the
        window that matters, because a worker tick fires faster than the
        refresh interval.
        """
        return max(self.spent, self.local)


class _Chain:
    """Per-process bookkeeping. One lock, three short critical sections."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state: dict[str, _State] = {}
        self._refreshed_at: float = 0.0
        self._day: str = ""

    # --- reading ---

    def _refresh_locked(self) -> None:
        today = datetime.now(timezone.utc).date().isoformat()
        # `bool(self._day)` is load-bearing. Without it the FIRST refresh in a
        # process looks like a day roll - the remembered day is "" and today is
        # not - and clears every cooldown, including one set moments earlier by
        # the 429 that is the whole reason this class exists. The symptom is a
        # rate-limited key being tried again immediately, forever.
        rolled = bool(self._day) and today != self._day
        fresh = time.monotonic() - self._refreshed_at < _SPEND_TTL_SECONDS
        if fresh and not rolled and self._day:
            return

        # Imported here rather than at module scope: the service imports the
        # config, the config imports this package, and a top-level import would
        # close the loop.
        from ..services import brain_usage_service

        try:
            spent = brain_usage_service.spend_today()
        except Exception:
            # A database that cannot be read is not a reason to stop
            # generating. Keep the counts we have; the 429 handler is still
            # the real backstop.
            log.warning("could not refresh credential spend", exc_info=True)
            return

        if rolled:
            # A new UTC day: the counts start over, and so does every
            # write-off that was only meant to last until the reset.
            for state in self._state.values():
                state.cooldown_until = 0.0
        self._day = today

        for label, state in self._state.items():
            state.spent = spent.get(label, 0)
            if rolled:
                # Only a new day resets the local counter. Clearing it on an
                # ordinary refresh would drop every attempt made since the
                # last one, which is exactly the set the database has not been
                # told about yet.
                state.local = 0
        for label, count in spent.items():
            if label not in self._state:
                self._state[label] = _State(spent=count)
        self._refreshed_at = time.monotonic()

    def _state_for(self, label: str) -> _State:
        return self._state.setdefault(label, _State())

    @staticmethod
    def _rpm_exhausted(state: _State, credential: Credential, now: float) -> bool:
        """Whether this credential has already spent its per-minute budget.

        Prunes the window as a side effect, so a credential that has gone
        quiet for a while does not carry a minute-old timestamp into the next
        check.
        """
        if not credential.rpm:
            return False
        while state.recent_calls and now - state.recent_calls[0] >= _RPM_WINDOW_SECONDS:
            state.recent_calls.popleft()
        return len(state.recent_calls) >= credential.rpm

    def candidates(
        self, *, structured: bool = False, max_attempts: int = DEFAULT_MAX_ATTEMPTS
    ) -> list[tuple[Credential, Any, str]]:
        """`(credential, provider, model)` for each credential worth trying now."""
        from . import llm

        chain = get_settings().llm_chain
        out: list[tuple[Credential, Any, str]] = []

        with self._lock:
            self._refresh_locked()
            now = time.monotonic()
            for credential in chain:
                if len(out) >= max_attempts:
                    break
                if not llm.usable(credential):
                    continue
                provider, model = llm.PROVIDERS[credential.provider], ""
                if structured and not provider.capabilities.structured_output:
                    continue
                state = self._state_for(credential.label)
                if state.cooldown_until > now:
                    continue
                if credential.daily_cap and state.used >= credential.daily_cap:
                    continue
                if self._rpm_exhausted(state, credential, now):
                    continue
                _, model = llm.resolve(credential)
                out.append((credential, provider, model))
        return out

    def unavailable(self) -> str:
        """Why nothing was tried, in one line, for the exception message.

        This is the single most useful sentence a health endpoint can carry on
        a bad day, so it is built even when nothing is wrong with the code.
        """
        from . import llm

        chain = get_settings().llm_chain
        if not chain:
            return "no credentials configured"

        with self._lock:
            now = time.monotonic()
            parts = []
            for credential in chain:
                state = self._state_for(credential.label)
                if not llm.usable(credential):
                    reason = "not configured"
                elif state.cooldown_until > now:
                    reason = f"cooling {int(state.cooldown_until - now)}s"
                elif credential.daily_cap and state.used >= credential.daily_cap:
                    reason = f"{state.used}/{credential.daily_cap}"
                elif self._rpm_exhausted(state, credential, now):
                    reason = f"{len(state.recent_calls)}/{credential.rpm} this minute"
                else:
                    reason = "available"
                parts.append(f"{credential.label} {reason}")
        return ", ".join(parts)

    # --- writing ---

    def note_attempt(self, credential: Credential) -> None:
        with self._lock:
            state = self._state_for(credential.label)
            state.local += 1
            if credential.rpm:
                state.recent_calls.append(time.monotonic())

    def note_success(self, credential: Credential) -> None:
        with self._lock:
            self._state_for(credential.label).cooldown_until = 0.0

    def note_failure(self, credential: Credential, exc: BaseException) -> None:
        with self._lock:
            state = self._state_for(credential.label)
            if is_rate_limit_error(exc):
                # A burst, not an exhausted day - checked first because every
                # rate-limit failure also matches is_quota_error below, and the
                # short cooldown is the one that must win. Sixty seconds is the
                # whole window; there is nothing to gain by waiting longer for
                # a limit that resets on its own.
                state.cooldown_until = time.monotonic() + _RATE_COOLDOWN_SECONDS
            elif is_quota_error(exc):
                # Out for the rest of the day, whatever the cap said. This is
                # the branch that matters when `daily_cap` is 0 or simply
                # wrong, which for a free-tier key whose real allowance Google
                # does not publish is the normal case rather than the odd one.
                state.cooldown_until = _next_utc_midnight()
                if credential.daily_cap:
                    state.spent = max(state.spent, credential.daily_cap)
            else:
                state.cooldown_until = time.monotonic() + _TRANSIENT_COOLDOWN_SECONDS

    def status(self) -> dict[str, dict[str, Any]]:
        """This process's view, for /api/health. Not for the admin board.

        Deliberately not exposed on the usage endpoint: these are one
        process's counters, the worker makes most of the calls, and a green
        tile drawn from the API process's memory would be a confident lie
        about a machine it cannot see.
        """
        with self._lock:
            now = time.monotonic()
            return {
                label: {
                    "spent_today": state.used,
                    "cooling_for": max(0, int(state.cooldown_until - now)),
                }
                for label, state in self._state.items()
            }

    def reset(self) -> None:
        """Forget everything. For tests, and for nothing else."""
        with self._lock:
            self._state.clear()
            self._refreshed_at = 0.0
            self._day = ""


CHAIN = _Chain()

candidates = CHAIN.candidates
note_attempt = CHAIN.note_attempt
note_success = CHAIN.note_success
note_failure = CHAIN.note_failure
unavailable = CHAIN.unavailable
status = CHAIN.status
