"""The one entry point for generated text.

Jurors, judges, moderators and the writing-help endpoints all call `generate()`
and nothing else. Which backend answers is a configuration detail none of them
can see.

    provider not credentialed  ->  deterministic offline generator
    provider credentialed      ->  LLM_PROVIDER (bedrock by default), falling
                                   back to offline on ANY error

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
    history: list[dict[str, str]] | None = None,
) -> str:
    """In-character text for a task. Never raises, never returns empty.

    `context` must be flat and JSON-serialisable - that constraint is what
    makes the offline seed reproducible and the model prompt trivial to build.

    `history` is the conversation so far, as `{"role", "content"}` turns, for
    the one task that has one: a private reply. The live backend sends them as
    real turns; the offline generator has no notion of a conversation and
    cannot become context-aware by being handed more context - but it still
    **seeds** on the turns, and that part matters. Its whole variety mechanism
    is a hash of its inputs, so a reply written from a context that does not
    change when the human says something new is the same reply, forever. The
    seed sees the conversation; the phrase bank does not.
    """
    context = context or {}
    settings = get_settings()

    if settings.use_llm:
        try:
            from . import llm

            text = llm.generate(
                personality_prompt, task, context, max_chars=max_chars, history=history
            )
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

    return offline.generate(
        personality_prompt,
        task,
        {**context, "turns": [turn["content"] for turn in history]} if history else context,
        max_chars=max_chars,
    )


def invent_lawsuit(
    personality_prompt: str,
    seed_extra: str = "",
    target: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """A complete filing for a bot acting on its own initiative.

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

    Every field is validated before it can reach an INSERT, and anything
    malformed falls back to the offline filing.
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
            log.warning("LLM filing failed; using the offline generator", exc_info=True)

    return offline.invent_lawsuit(personality_prompt, seed_extra, target)


def remember(personality_prompt: str, context: dict[str, Any]) -> dict[str, Any] | None:
    """Rewrite what a bot remembers about one person, or None.

    None is returned whenever the model did not answer - and there is
    deliberately no offline path. The other tasks degrade to a phrase bank and
    the worst case is a duller comment; a memory is a claim about a real person
    that the bot will repeat back to them for weeks. A generator that cannot
    read cannot summarise, and inventing what somebody told you is worse than
    remembering nothing.

    The consequence when the backend is down is mild and self-correcting: the
    stored memory simply stops advancing, the recent-window layer keeps working
    on its own, and the next successful call summarises everything that piled
    up in the meantime.
    """
    settings = get_settings()
    if not settings.use_llm:
        LAST_CALL.record_offline()
        return None

    try:
        from . import llm

        memory = llm.remember(personality_prompt, context)
        LAST_CALL.record_llm_ok()
        return memory
    except Exception as exc:
        LAST_CALL.record_llm_failure(exc)
        log.warning("memory rewrite failed; the old memory stands", exc_info=True)
        return None


__all__ = [
    "generate",
    "invent_lawsuit",
    "remember",
    "status",
    "LAST_CALL",
    "Task",
    "TASKS",
]
