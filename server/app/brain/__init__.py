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
"""

from __future__ import annotations

import logging
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
)


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
            return offline.trim(text, max_chars)
        except Exception:
            # Unknown provider, missing package, bad key, rate limit, timeout,
            # empty completion, network down - all the same from here: use the
            # offline brain.
            log.warning("LLM backend failed; using the offline generator", exc_info=True)

    return offline.generate(personality_prompt, task, context, max_chars=max_chars)


def invent_lawsuit(personality_prompt: str, seed_extra: str = "") -> dict[str, Any]:
    """A complete filing for a bot acting on its own initiative.

    Always offline: the structure (title, defendant, charges) has to be
    well-formed enough to insert, and free-form model output is not worth
    parsing for that.
    """
    return offline.invent_lawsuit(personality_prompt, seed_extra)


__all__ = ["generate", "invent_lawsuit", "Task", "TASKS"]
