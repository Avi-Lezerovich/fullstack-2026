"""The one entry point for generated text.

Jurors, judges, moderators and the writing-help endpoints all call `generate()`
and nothing else. Which backend answers is a configuration detail none of them
can see.

    provider not credentialed  ->  deterministic offline generator
    provider credentialed      ->  LLM_PROVIDER (bedrock by default), falling
                                   back to offline on ANY error

One caller opts out of that fallback: `invent_lawsuit(..., require_llm=True)`
returns None rather than an offline filing, because a case is a permanent
public row and the offline path has twelve fixed defendants. See its docstring.

`generate()` never raises and never returns an empty string. That is a
deliberate contract: a juror is in the middle of a database transaction when
this is called, and a failed API request must not roll back a trial.

**But failing open silently is how a dead backend hides.** `use_llm` is a
local, cheap check - for Bedrock it asks only "is AWS_REGION set?" - so it
reports the *intent* to call a model, never the outcome. With the `anthropic`
package missing from the image, every call raised ModuleNotFoundError, landed
in the `except` below, and produced perfectly plausible offline text while
/api/health cheerfully reported `"brain": "llm"`.

So the last outcome is recorded in `LAST_CALL` and reported by /api/health
alongside the intent. That costs one module-level assignment per call and is
the difference between "the model is answering" and "the model has never once
answered".
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Literal

from ..config import get_settings
from . import offline

log = logging.getLogger(__name__)

Task = Literal[
    "jury_deliberation",
    "verdict",
    "sentence",
    "moderation_note",
    "draft_lawsuit",
    "suggest_comment",
    "bot_lawsuit",
    "bot_comment",
    "bot_reply",
]

TASKS: tuple[str, ...] = (
    "jury_deliberation",
    "verdict",
    "sentence",
    "moderation_note",
    "draft_lawsuit",
    "suggest_comment",
    "bot_lawsuit",
    "bot_comment",
    "bot_reply",
)


class _LastCall:
    """What the most recent generate() actually did, for /api/health.

    Deliberately in-memory and per-process: this answers "is the backend
    working *right now, here*", which is a property of this container, not a
    fact worth a database round trip on every health poll. gunicorn runs
    several workers, so a poll may land on one that has not generated anything
    yet - hence the explicit "unknown" starting state rather than a lie in
    either direction.

    The lock keeps a torn read impossible under gthread workers; the whole
    critical section is three assignments.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.backend: str = "unknown"
        self.error: str | None = None
        self.llm_calls: int = 0
        self.llm_failures: int = 0

    def record_llm_ok(self) -> None:
        with self._lock:
            self.backend = "llm"
            self.error = None
            self.llm_calls += 1

    def record_llm_failure(self, exc: BaseException) -> None:
        with self._lock:
            self.backend = "offline"
            # The class name matters more than the message here:
            # ModuleNotFoundError, AccessDeniedException and ValidationException
            # are three completely different fixes.
            self.error = f"{type(exc).__name__}: {exc}"[:300]
            self.llm_calls += 1
            self.llm_failures += 1

    def record_offline(self) -> None:
        with self._lock:
            self.backend = "offline"
            self.error = None

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "last_backend": self.backend,
                "last_error": self.error,
                "llm_calls": self.llm_calls,
                "llm_failures": self.llm_failures,
            }


LAST_CALL = _LastCall()


def status() -> dict[str, Any]:
    """What /api/health reports about the brain.

    `configured` is the intent (what settings say we will try), `last_backend`
    is the outcome (what actually answered). When those two disagree, the
    backend is broken and `last_error` says how.
    """
    settings = get_settings()
    return {"configured": "llm" if settings.use_llm else "offline", **LAST_CALL.snapshot()}


def generate(
    personality_prompt: str,
    task: str,
    context: dict[str, Any] | None = None,
    *,
    max_chars: int = offline.DEFAULT_MAX_CHARS,
) -> str:
    """In-character text for a task. Never raises, never returns empty.

    `context` must be flat and JSON-serialisable - that constraint is what
    makes the offline seed reproducible and the model prompt trivial to build.
    """
    context = context or {}
    settings = get_settings()

    if settings.use_llm:
        try:
            from . import llm

            text = llm.generate(personality_prompt, task, context, max_chars=max_chars)
            LAST_CALL.record_llm_ok()
            return offline.trim(text, max_chars)
        except Exception as exc:
            # Unknown provider, missing package, bad key, rate limit, timeout,
            # empty completion, network down - all the same from here: use the
            # offline brain. Recorded so it is not also *invisible* from here.
            LAST_CALL.record_llm_failure(exc)
            log.warning("LLM backend failed; using the offline generator", exc_info=True)
    else:
        LAST_CALL.record_offline()

    return offline.generate(personality_prompt, task, context, max_chars=max_chars)


def invent_lawsuit(
    personality_prompt: str,
    seed_extra: str = "",
    target: dict[str, Any] | None = None,
    *,
    require_llm: bool = False,
) -> dict[str, Any] | None:
    """A complete filing for a bot acting on its own initiative.

    `require_llm=True` turns the usual fall-back-to-offline contract off for
    this one call: when the model is not configured, or the call fails, the
    answer is None and **no filing is invented at all**. Every other task in
    this module still fails open, because a juror who says nothing stalls a
    trial - but a case is a permanent row on the public feed, and the offline
    generator draws its defendants from a fixed list of twelve. A backend
    outage that lasts an afternoon therefore does not degrade the feed, it
    fills it with the same lawsuit over and over, under different names. The
    caller skips its turn instead.

    The live model writes these when it can. That is a change of mind from the
    original design, which kept filings offline because "free-form model output
    is not worth parsing": with a JSON schema on the response it is no longer
    free-form, and the offline path's twelve fixed defendants were the single
    most visible source of repetition in the feed - the same "התביעה נגד
    הקפה שהתקרר" filed by three different bots in one afternoon.

    `target` says who is being sued - a thing, something topical, or another
    one of the court's personalities. It never says "a human": that rule is
    enforced in the worker, against the database, because only there is there
    anything to check a name against.

    Every field is validated before it can reach an INSERT; anything malformed
    is a failed call, and lands wherever this call's `require_llm` says.
    """
    settings = get_settings()

    if settings.use_llm:
        try:
            from . import llm

            filing = llm.invent_lawsuit(personality_prompt, seed_extra, target)
            LAST_CALL.record_llm_ok()
            return filing
        except Exception as exc:
            LAST_CALL.record_llm_failure(exc)
            if require_llm:
                log.warning("LLM filing failed; no case filed", exc_info=True)
                return None
            log.warning("LLM filing failed; using the offline generator", exc_info=True)
    elif require_llm:
        # Not an error and not worth a warning on every tick: the whole
        # application is designed to run with nothing configured.
        LAST_CALL.record_offline()
        log.info("no LLM backend configured; no case filed")
        return None

    return offline.invent_lawsuit(personality_prompt, seed_extra, target)


__all__ = ["generate", "invent_lawsuit", "status", "LAST_CALL", "Task", "TASKS"]
