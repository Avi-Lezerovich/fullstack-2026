"""The one entry point for generated text.

Jurors, judges, moderators and the writing-help endpoints all call `generate()`
and nothing else. Which backend answers is a configuration detail none of them
can see.

    provider not credentialed  ->  deterministic offline generator
    provider credentialed      ->  LLM_PROVIDER (bedrock by default), falling
                                   back to offline on ANY error

One caller opts out of that fallback: `invent_lawsuit(..., require_llm=True)`
returns None rather than an offline filing, because a case is a permanent
public row and the offline path draws from a fixed list. See its docstring.

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

**And a backend that answers can still be a backend that cannot comply.** The
gateway provider has no structured output; asking it for a lawsuit produced a
plausible answer with a schema that had been *suggested* rather than enforced,
and no layer above could tell the difference. So the tasks that need a
guarantee - a vote, a filing, a memory - ask `llm.capabilities()` first and
take the deterministic path when the answer is no, recording which capability
was missing. A degraded backend now looks degraded rather than looking like a
model having a bad day.
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
    "bot_comment_reply",
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
    "bot_comment_reply",
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
        # Prompt caching is the one optimisation in here that fails SILENTLY -
        # the requests keep succeeding and only the bill moves - and it
        # characteristically breaks later, when somebody adds a field to the
        # system prompt, rather than when it is written. Counting reads is the
        # only ground truth that it still works, and putting the counter on the
        # health endpoint is what makes anyone ever look at it.
        self.cache_reads: int = 0
        self.cache_writes: int = 0
        # Which provider capability a task wanted and could not have. Distinct
        # from `error`: nothing failed, the backend simply cannot do this.
        self.missing: str | None = None

    def record_llm_ok(self, usage: Any = None) -> None:
        with self._lock:
            self.backend = "llm"
            self.error = None
            self.missing = None
            self.llm_calls += 1
            if usage is not None:
                self.cache_reads += int(getattr(usage, "cache_read", 0) or 0)
                self.cache_writes += int(getattr(usage, "cache_write", 0) or 0)

    def record_llm_failure(self, exc: BaseException) -> None:
        with self._lock:
            self.backend = "offline"
            # The class name matters more than the message here:
            # ModuleNotFoundError, AccessDeniedException and ValidationException
            # are three completely different fixes.
            self.error = f"{type(exc).__name__}: {exc}"[:300]
            self.llm_calls += 1
            self.llm_failures += 1

    def record_offline(self, missing: str | None = None) -> None:
        with self._lock:
            self.backend = "offline"
            self.error = None
            self.missing = missing

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "last_backend": self.backend,
                "last_error": self.error,
                "llm_calls": self.llm_calls,
                "llm_failures": self.llm_failures,
                "cache_reads": self.cache_reads,
                "cache_writes": self.cache_writes,
                "missing_capability": self.missing,
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

    `max_chars` is a **token budget and an offline template length**, not a cut
    applied to a model's answer. How long a live answer runs is decided by the
    character and by the length angle it drew, which is where variety in the
    feed comes from; see `offline.tidy`.

    `history` is the conversation so far, as `{"role", "content"}` turns, for
    the one task that has one: a private reply. The live backend sends them as
    real turns; the offline generator has no notion of a conversation and
    cannot become context-aware by being handed more context - but it still
    **seeds** on the turns, and that part matters. Its whole variety mechanism
    is a hash of its inputs, so a reply written from a context that does not
    change when the human says something new is the same reply, forever. The
    seed sees the conversation; the minute it writes does not.
    """
    context = context or {}
    settings = get_settings()

    if settings.use_llm:
        try:
            from . import llm

            completion = llm.generate(
                personality_prompt, task, context, max_chars=max_chars, history=history
            )
            LAST_CALL.record_llm_ok(completion)
            # Not trimmed to `max_chars`: how long this is belongs to the
            # character and the angle it drew, not to the caller's token budget.
            return offline.tidy(completion.text)
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
    *,
    require_llm: bool = False,
) -> dict[str, Any] | None:
    """A complete filing for a bot acting on its own initiative.

    `require_llm=True` turns the usual fall-back-to-offline contract off for
    this one call: when the model is not configured, or the call fails, the
    answer is None and **no filing is invented at all**. Every other task in
    this module still fails open, because a juror who says nothing stalls a
    trial - but a case is a permanent row on the public feed, and the offline
    generator draws its defendants from one fixed list. A backend
    outage that lasts an afternoon therefore does not degrade the feed, it
    fills it with the same handful of lawsuits over and over, under
    different names. The caller skips its turn instead.

    The live model writes these when it can. That is a change of mind from the
    original design, which kept filings offline because "free-form model output
    is not worth parsing": with a JSON schema on the response it is no longer
    free-form, and the offline path's fixed defendant list was the single
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
    from . import llm

    # A filing is the clearest case for the capability gate. Without an
    # enforced schema the "defendant" field is a suggestion, and the one rule
    # this application cannot bend - a bot may never sue a person - is checked
    # against exactly that field in the worker. Better to file nothing.
    if settings.use_llm and llm.capabilities().structured_output:
        try:
            filing = llm.invent_lawsuit(personality_prompt, seed_extra, target)
            LAST_CALL.record_llm_ok(filing.pop("usage", None))
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
        missing = "structured_output" if settings.use_llm else None
        LAST_CALL.record_offline(missing)
        log.info("no filing: %s", missing or "no LLM backend configured")
        return None

    return offline.invent_lawsuit(personality_prompt, seed_extra, target)


def remember(personality_prompt: str, context: dict[str, Any]) -> dict[str, Any] | None:
    """Rewrite what a bot remembers about one person, or None.

    None is returned whenever the model did not answer - and there is
    deliberately no offline path. The other tasks degrade to a clerical minute
    and the worst case is a duller comment; a memory is a claim about a real person
    that the bot will repeat back to them for weeks. A generator that cannot
    read cannot summarise, and inventing what somebody told you is worse than
    remembering nothing.

    The consequence when the backend is down is mild and self-correcting: the
    stored memory simply stops advancing, the raw layers keep working on their
    own, and the next successful call summarises everything that piled up in
    the meantime. That self-correction is only true because the evidence is
    still there - see the note above `remember` in llm.py.
    """
    settings = get_settings()
    from . import llm

    if not settings.use_llm or not llm.capabilities().structured_output:
        LAST_CALL.record_offline("structured_output" if settings.use_llm else None)
        return None

    try:
        memory = llm.remember(personality_prompt, context)
        LAST_CALL.record_llm_ok(memory.pop("usage", None))
        return memory
    except Exception as exc:
        LAST_CALL.record_llm_failure(exc)
        log.warning("memory rewrite failed; the old memory stands", exc_info=True)
        return None


def deliberate(
    personality_prompt: str,
    context: dict[str, Any],
    *,
    guilt_bias: float,
    case_id: int,
    juror_user_id: int,
    salt: str = "",
) -> dict[str, str]:
    """One juror: how they vote, and what they say. Never raises.

    Two regimes, and the docstring in `decide.py` names the difference:

    * **With a model that can enforce an enum**, the juror decides. The vote and
      the line come out of one structured call, so the argument in the room and
      the number in the tally are the same act. A juror can be talked round by
      the case in front of it, which is what a deliberation is for.
    * **Otherwise** - no credentials, a provider that cannot enforce a schema,
      or a failed call - `decide.decide_vote` decides from `guilt_bias`, the
      vote is passed *into* the prose so the two still agree, and the whole
      thing stays byte-reproducible from (case, juror).

    Either way this returns a vote, because a juror who says nothing stalls a
    trial. The engine's idempotency does not rest on which regime ran: vote and
    comment commit together, guarded by `comments.dedupe_key` and
    `spoke_at IS NULL`, so a retry either finds the work done or redoes all of
    it.
    """
    from . import llm
    from .decide import decide_vote

    settings = get_settings()

    if settings.use_llm and llm.capabilities().structured_output:
        try:
            spoken = llm.deliberate(personality_prompt, context, guilt_bias=guilt_bias)
            LAST_CALL.record_llm_ok(spoken.pop("usage", None))
            return {
                "vote": spoken["vote"],
                "line": offline.tidy(spoken["line"]),
            }
        except Exception as exc:
            LAST_CALL.record_llm_failure(exc)
            log.warning("deliberation failed; falling back to the dial", exc_info=True)

    vote = decide_vote(
        guilt_bias=guilt_bias,
        case_id=case_id,
        juror_user_id=juror_user_id,
        salt=salt,
        context=context,
    )
    # The vote goes into the context the prose is written from. Without it the
    # fallback reproduces the original bug in miniature - a juror arguing one
    # way and being counted the other - which is the whole reason this function
    # returns both halves rather than letting the caller assemble them.
    line = generate(
        personality_prompt, "jury_deliberation", {**context, "your_vote": vote}
    )
    return {"vote": vote, "line": line}


__all__ = [
    "generate",
    "deliberate",
    "invent_lawsuit",
    "remember",
    "status",
    "LAST_CALL",
    "Task",
    "TASKS",
]
