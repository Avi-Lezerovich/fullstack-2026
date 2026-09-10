"""The optional live backend - one provider-neutral seam.

Only used when the configured provider is actually credentialed. The provider
SDK is imported inside its completion function so the package stays genuinely
optional - the application, the test suite and the Docker image all still run
without it, on the offline generator.

Adding a provider is one entry in `PROVIDERS` and nothing else. Everything
above this module - the prompt, the tasks, the callers - is unchanged by that,
which is the whole reason no vendor is named outside this file.

Providers do not agree on what "credentialed" means, so each one says for
itself: Bedrock authenticates through the AWS credential chain and has no API
key at all, while the direct Anthropic API has nothing but one.

This module is allowed to raise. Every failure mode - unknown provider, missing
package, missing credentials, bad key, rate limit, timeout, empty completion,
network down - lands in the same `except` in brain/__init__.py and falls back to
the offline generator. The worker therefore has no LLM-shaped failure mode.

This is a package rather than a single file, split by concern:

    prompt.py             the prompt-engineering layer - angles, blocks, briefs
    providers/base.py     the two SDK-backed providers (Bedrock, Anthropic)
    providers/gateway.py  the API-Gateway-fronted provider (degraded)
    providers/gemini.py   the Gemini HTTP provider (real schema, no SDK)
    registry.py           PROVIDERS and what each credential can do
    tasks.py              generate/deliberate/invent_lawsuit/remember

Every name that used to live directly on this module is re-exported below, so
`from app.brain import llm; llm.generate(...)` and
`from app.brain.llm import generate` both still work exactly as before the
split - including the test suite's private-attribute reaches into
`llm.urllib.request` and `llm.time.sleep`, which is why `time` and
`urllib.request` are imported here too rather than only in the submodules that
happen to use them.
"""

from __future__ import annotations

import json
import logging
import random
import time
import urllib.error
import urllib.request

from .prompt import (
    HOOKS,
    LENGTHS,
    MOVES,
    SHARED_SYSTEM,
    STYLE_RULES,
    SYSTEM_PREAMBLE,
    TASK_BRIEFS,
    _CONTEXT_LABELS,
    _DEFAULT_EFFORT,
    _EFFORT_BY_TASK,
    _KNOWS_OUTCOME,
    _LONG_FORM,
    _NO_ANGLE,
    _OUTCOME_FIELDS,
    _THINKING,
    _VERDICT_WORDS,
    _cache_control,
    _max_tokens_for,
    _text_of,
    build_prompt,
    build_system,
    effort_for,
    pick_angle,
)
from .providers.base import (
    Completion,
    _complete_anthropic,
    _complete_bedrock,
    _complete_sdk,
    _output_config,
    _usage_of,
)
from .providers.gateway import (
    _GATEWAY_TEXT_KEYS,
    _TURN_LABELS,
    _complete_gateway,
    _flatten,
    _flatten_system,
    _strip_fence,
)
from .providers.gemini import (
    _GEMINI_ATTEMPTS,
    _GEMINI_BACKOFF_CAP_SECONDS,
    _GEMINI_DEFAULT_THINKING,
    _GEMINI_ERROR_BODY_CHARS,
    _GEMINI_HOST,
    _GEMINI_RETRY_STATUS,
    _GEMINI_ROLES,
    _GEMINI_SCHEMA_DROP,
    _GEMINI_THINKING_HEADROOM,
    _GEMINI_THINKING_LEVELS,
    GeminiHttpError,
    _complete_gemini,
    _gemini_http_error,
    _gemini_post,
    _gemini_schema,
    _gemini_thinks,
)
from .registry import (
    GATEWAY_CAPABILITIES,
    PROVIDERS,
    SDK_CAPABILITIES,
    Capabilities,
    Provider,
    capabilities,
    is_configured,
    resolve,
    usable,
)
from .tasks import (
    DELIBERATION_SCHEMA,
    FILING_BRIEF,
    LAWSUIT_SCHEMA,
    MEMORY_BRIEF,
    MEMORY_SCHEMA,
    TARGET_BRIEFS,
    AllCredentialsFailed,
    Attempt,
    _DISPOSITIONS,
    _clean_charge,
    _target_section,
    _try_chain,
    deliberate,
    disposition_of,
    generate,
    invent_lawsuit,
    log,
    remember,
)

__all__ = [
    "AllCredentialsFailed",
    "Attempt",
    "Capabilities",
    "Completion",
    "DELIBERATION_SCHEMA",
    "FILING_BRIEF",
    "GATEWAY_CAPABILITIES",
    "GeminiHttpError",
    "HOOKS",
    "LAWSUIT_SCHEMA",
    "LENGTHS",
    "MEMORY_BRIEF",
    "MEMORY_SCHEMA",
    "MOVES",
    "PROVIDERS",
    "Provider",
    "SDK_CAPABILITIES",
    "SHARED_SYSTEM",
    "STYLE_RULES",
    "SYSTEM_PREAMBLE",
    "TARGET_BRIEFS",
    "TASK_BRIEFS",
    "build_prompt",
    "build_system",
    "capabilities",
    "deliberate",
    "disposition_of",
    "effort_for",
    "generate",
    "invent_lawsuit",
    "is_configured",
    "pick_angle",
    "remember",
    "resolve",
    "usable",
]
