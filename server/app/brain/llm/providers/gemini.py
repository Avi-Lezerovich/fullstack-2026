"""Google Gemini over plain HTTP - no SDK, and a real schema."""

from __future__ import annotations

import json
import random
import time
import urllib.error
import urllib.request
from typing import Any

from ....config import get_settings
from .base import Completion
from .gateway import _flatten_system

_GEMINI_HOST = "https://generativelanguage.googleapis.com/v1beta"

# Gemini's `responseSchema` is an OpenAPI subset, not full JSON Schema. It
# rejects the keywords below outright with a 400, so they are dropped on the
# way in rather than being discovered in production: `additionalProperties` is
# the one that matters, because LAWSUIT_SCHEMA sets it and every filing would
# fail without this.
_GEMINI_SCHEMA_DROP = frozenset({"additionalProperties", "$schema", "definitions", "$defs"})

# Transient on Google's side, and worth a second ask. 503 is the one that
# matters: the free tier is shared with everyone else on the free tier, so at
# peak it is the normal answer rather than the exceptional one - a measured
# 9 failures in 10 during one evening, all of them 503. Google's own SDKs retry
# these by default with exponential backoff; this provider is written against
# urllib, so it has to say so itself. Everything else - 400, 401, 403 - is a
# fault in the request that a retry would only repeat.
_GEMINI_RETRY_STATUS = frozenset({408, 429, 500, 502, 503, 504})

# Three tries, not ten. Every call here sits on a worker tick or a user's
# request, and the caller already has a working answer to fall back on, so the
# right shape is "ride out a blip" rather than "wait out an outage". With the
# jitter below the added delay tops out near six seconds.
_GEMINI_ATTEMPTS = 3
_GEMINI_BACKOFF_CAP_SECONDS = 4.0

# Gemini 3.x thinks before it answers, and - exactly as the Messages API does -
# it charges those thinking tokens against `maxOutputTokens`. Left at the
# model's own default the bill is steep and mostly invisible. Measured against
# gemini-3-flash-preview with one short Hebrew sentence:
#
#     default (high)                 15.7s    429 thinking tokens
#     thinkingConfig.thinkingLevel    8.4s    477
#     thinkingConfig.thinkingBudget   1.0s      0
#
# Latency is the smaller half. The larger half is that a filing asks for a
# schema inside the SAME token budget the thinking is eating, so a model left
# on `high` spends the budget reasoning and returns JSON cut mid-string - which
# arrives here as a JSONDecodeError and reads as a model that cannot follow a
# schema rather than one that was never given room to finish.
#
# `effort_for()` already returns exactly Gemini's vocabulary - "low" for court
# chatter, "medium" for the tasks worth thinking about - so the dial this
# module was already being handed simply had to be passed on. Note the nesting:
# `generationConfig.thinkingLevel` is rejected with "Unknown name", it belongs
# under `thinkingConfig`.
#
# This is a Gemini 3.x field. A 2.x model configured here would reject it, and
# would do so as a 400, which is deliberately not retried - it fails fast and
# lands in LAST_CALL rather than being quietly swallowed three times over.
_GEMINI_THINKING_LEVELS = frozenset({"minimal", "low", "medium", "high"})
_GEMINI_DEFAULT_THINKING = "low"

# Headroom ON TOP of the text budget, not a cap on thinking. Setting the level
# alone is not enough, and the measurements say why - a filing with a 2048
# budget, twice in five attempts:
#
#     no thinkingConfig   think=1963  finish=MAX_TOKENS  JSON cut at char 148
#     thinkingLevel=med   think=1962  finish=MAX_TOKENS  JSON cut at char 161
#     thinkingLevel=med   think= 883  finish=STOP        505 characters, fine
#     thinkingLevel=low   think=   0  finish=STOP        721 characters, fine
#
# Thinking is variable and it is charged against the same counter as the
# answer, so a budget sized for the text alone is one the model can spend
# entirely on reasoning before writing a single character. "medium" is what
# `effort_for` returns for a filing - the task that most needs the room and is
# least able to survive losing it, since a truncated schema is a failed call
# rather than a shorter answer.
#
# Generous on purpose: output is billed on what is generated, so unused
# headroom costs nothing, while too little costs the whole call.
#
# Sized for the TAIL, not the average, because thinking is wildly variable.
# Six filings at "medium" on one run spent 1140, 1305, 2785, 4104 and 4912
# tokens thinking. A headroom of 3072 covered the middle of that spread and
# still lost the call that wanted 4912 - so the number below is not "what a
# filing usually needs", it is "what the greediest one observed needed, with
# room to spare". Averages are the wrong statistic for a budget whose only
# failure mode is running out.
_GEMINI_THINKING_HEADROOM = {"minimal": 0, "low": 512, "medium": 8192, "high": 12288}


def _gemini_thinks(model: str) -> bool:
    """Whether `thinkingConfig.thinkingLevel` is a field this model has.

    It is a 3.x field. A 2.x model answers it with a 400 naming the unknown
    field - and 400 is deliberately not retried, so it fails fast, once per
    call, on every call, which is indistinguishable on a dashboard from a
    dead key. That is not hypothetical: the comment above predicted it, and
    the 2.5 Flash-Lite line is the one worth configuring here, because it is
    the model whose free tier is measured in thousands of requests a day
    rather than tens.
    """
    return model.startswith("gemini-3")


# How much of Google's error body to keep. Long enough for the sentence that
# names the model or the quota metric, short enough to survive the VARCHAR(300)
# that `fallback_reason` is stored in.
_GEMINI_ERROR_BODY_CHARS = 400


class GeminiHttpError(Exception):
    """An HTTP error from Google, WITH the body that says what went wrong.

    `urllib.error.HTTPError` stringifies to "HTTP Error 404: Not Found" and
    nothing else. The sentence that actually identifies the fault - "models/
    gemini-3.7-flash is not found for API version v1beta", or the name of the
    exhausted quota metric - is in the response body, which is readable exactly
    once and is otherwise dropped on the floor. That loss is not academic: it
    is the difference between an operator reading their dashboard and knowing
    the model id is wrong, and reading "HTTP Error 404" and guessing.

    `.code` is kept as an attribute rather than only in the message so callers
    can branch on it without parsing prose.
    """

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code


def _gemini_http_error(exc: urllib.error.HTTPError) -> GeminiHttpError:
    """Read the body while it is still readable, and name the fault with it.

    Google answers with `{"error": {"code", "message", "status"}}`, and only
    `message` says anything a person can act on. Unwrapping it rather than
    keeping the raw JSON is not tidiness: the message is stored in a bounded
    column and grouped, on the dashboard, by its first 80 characters - and the
    envelope alone is 45 of them, so a raw body would spend the whole budget on
    punctuation and truncate immediately before the model id that identifies
    the fault. The envelope is kept only when it is not the shape we expect.
    """
    try:
        raw = exc.read().decode("utf-8", "replace").strip()
    except Exception:  # pragma: no cover - a body that cannot be read at all
        raw = ""

    detail = ""
    try:
        error = json.loads(raw).get("error") or {}
        detail = " ".join(
            str(part) for part in (error.get("status"), error.get("message")) if part
        )
    except (ValueError, AttributeError):
        detail = raw

    detail = " ".join(detail.split())[:_GEMINI_ERROR_BODY_CHARS]
    return GeminiHttpError(exc.code, f"gemini HTTP {exc.code}: {detail or exc.reason}")


def _gemini_post(request: urllib.request.Request, timeout: float) -> dict[str, Any]:
    """POST with backoff on the failures that are Google being busy.

    The jitter is not decoration. Every bot on this site shares one API key and
    the worker fires them on a fixed tick, so a fixed backoff would line the
    retries up into exactly the thundering herd the retry is meant to survive.

    Every HTTPError is converted to a `GeminiHttpError` at the point it is
    caught, because `exc.read()` works once and only before the exception has
    been passed around - so it has to happen here or not at all.
    """
    last: Exception | None = None
    for attempt in range(_GEMINI_ATTEMPTS):
        if attempt:
            delay = min(_GEMINI_BACKOFF_CAP_SECONDS, 2.0**attempt)
            time.sleep(delay * (0.5 + random.random()))
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            error = _gemini_http_error(exc)
            if exc.code not in _GEMINI_RETRY_STATUS:
                raise error from None
            last = error
        except (TimeoutError, urllib.error.URLError) as exc:
            last = exc
    assert last is not None
    raise last


# Anthropic says "assistant", Gemini says "model". The only role that differs.
_GEMINI_ROLES = {"assistant": "model", "user": "user", "model": "model"}


def _gemini_schema(node: Any) -> Any:
    """A JSON Schema, minus the keywords Gemini's validator refuses."""
    if isinstance(node, dict):
        return {
            key: _gemini_schema(value)
            for key, value in node.items()
            if key not in _GEMINI_SCHEMA_DROP
        }
    if isinstance(node, list):
        return [_gemini_schema(item) for item in node]
    return node


def _complete_gemini(
    system: list[dict[str, Any]],
    messages: list[dict[str, str]],
    *,
    credential,
    model: str,
    max_tokens: int,
    effort: str,
    output_format: dict[str, Any] | None = None,
    stream: bool = False,
) -> Completion:
    """Google's Gemini over plain HTTP - no SDK, and a real schema.

    This is the provider for a box with no AWS identity that still needs
    structured output, which is exactly the gap the gateway leaves. Gemini
    enforces `responseSchema` server-side the way Bedrock does, so filings,
    juror votes and memory rewrites are all routed here - see `capabilities()`.

    Written against `urllib` on purpose. The one thing this needs that the
    gateway does not is a schema, and that is a field in a JSON body rather
    than an SDK feature, so a dependency would buy nothing and would have to be
    installed in an image that currently ships without it.

    Three deliberate differences from the SDK providers:

    * **The key travels in a header, not the query string.** Google documents
      `?key=`, which puts a live credential into every proxy log and crash
      report between here and them. `x-goog-api-key` is equally supported and
      is the only responsible choice.
    * **No prompt caching.** Gemini's implicit cache needs no breakpoints, so
      the ordered blocks are simply concatenated. Nothing is lost that this
      provider could have expressed; the usage counters come back zero, which
      is honest rather than a silent zero.
    * **`stream` is accepted and ignored.** It exists on the SDK path so a slow
      filing does not trip the HTTP timeout. Flash models answer a filing in a
      couple of seconds against a 60s timeout, so the streaming endpoint would
      add SSE parsing to buy nothing. If a slower Gemini model is ever
      configured here, this is the first thing to revisit.
    """
    if not credential.api_key:
        raise ValueError(f"credential {credential.label!r} has no API key")

    level = effort if effort in _GEMINI_THINKING_LEVELS else _GEMINI_DEFAULT_THINKING

    body: dict[str, Any] = {
        "systemInstruction": {"parts": [{"text": _flatten_system(system)}]},
        "contents": [
            {
                "role": _GEMINI_ROLES.get(message["role"], "user"),
                "parts": [{"text": message["content"]}],
            }
            for message in messages
        ],
        "generationConfig": {"maxOutputTokens": max_tokens},
    }
    if _gemini_thinks(model):
        # The headroom is added only alongside the dial that makes it
        # necessary: without thinking, `max_tokens` is spent on the answer
        # alone and the extra budget would only raise the ceiling on a
        # runaway generation.
        body["generationConfig"]["maxOutputTokens"] += _GEMINI_THINKING_HEADROOM[level]
        body["generationConfig"]["thinkingConfig"] = {"thinkingLevel": level}
    if output_format is not None:
        body["generationConfig"]["responseMimeType"] = "application/json"
        body["generationConfig"]["responseSchema"] = _gemini_schema(
            output_format.get("schema", {})
        )

    request = urllib.request.Request(
        f"{_GEMINI_HOST}/models/{model}:generateContent",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": credential.api_key,
        },
    )
    payload = _gemini_post(request, get_settings().llm_timeout_seconds)

    # A blocked prompt comes back 200 with no candidates at all. Saying so
    # beats "empty completion from gemini", which would send the caller looking
    # for a network fault that is not there.
    blocked = (payload.get("promptFeedback") or {}).get("blockReason")
    if blocked:
        raise ValueError(f"gemini blocked the prompt ({blocked})")

    candidates = payload.get("candidates") or []
    if not candidates:
        raise ValueError("no candidates from gemini")

    candidate = candidates[0]
    finish = candidate.get("finishReason", "")
    if finish and finish not in ("STOP", "MAX_TOKENS"):
        raise ValueError(f"gemini stopped early ({finish})")

    # MAX_TOKENS plus a schema means JSON cut mid-string. Letting that reach
    # json.loads produces "Unterminated string starting at char 148", which
    # reads as a model that cannot follow a schema - the wrong culprit, and one
    # that sends you looking at the prompt instead of at the budget. Thinking
    # is charged against this same counter and is what usually eats it, so say
    # that here, where the numbers to say it with are still in scope.
    if finish == "MAX_TOKENS" and output_format is not None:
        thoughts = (payload.get("usageMetadata") or {}).get("thoughtsTokenCount", 0)
        raise ValueError(
            f"gemini ran out of output budget before finishing the schema "
            f"(limit {body['generationConfig']['maxOutputTokens']}, "
            f"{thoughts} of it spent thinking at level {level!r})"
        )

    text = "".join(
        part.get("text", "")
        for part in ((candidate.get("content") or {}).get("parts") or [])
    ).strip()
    if not text:
        raise ValueError(f"empty completion from gemini ({finish or 'no reason given'})")

    usage = payload.get("usageMetadata") or {}
    return Completion(
        text=text,
        input_tokens=int(usage.get("promptTokenCount", 0) or 0),
        output_tokens=int(usage.get("candidatesTokenCount", 0) or 0),
    )
