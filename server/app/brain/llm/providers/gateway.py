"""The API-Gateway-fronted provider - degraded, and honest about it."""

from __future__ import annotations

import json
import urllib.request
from typing import Any

from ....config import get_settings
from .base import Completion

# The keys a gateway might name its completion, best first. The endpoint this
# was built against returns `text`; the others cost nothing to accept and save
# the next person a debugging session if theirs differs.
_GATEWAY_TEXT_KEYS = ("text", "completion", "response", "output")


# Labels for the transcript the gateway provider has to be handed as text.
# "אתה" for the assistant side is deliberate: the string is read by the model
# as its own past speech, and third-person ("הבוט אמר") reliably produced
# answers that discussed the character instead of being it.
_TURN_LABELS = {"assistant": "אתה", "user": "הוא"}


def _flatten(messages: list[dict[str, str]]) -> str:
    """One string for an endpoint that accepts exactly one string.

    A single-turn call renders as just its content - unchanged from before
    turns existed, which is what keeps every non-conversational task byte-
    identical to what it was.
    """
    if len(messages) == 1:
        return messages[0]["content"]
    return "\n\n".join(
        f"{_TURN_LABELS.get(message['role'], message['role'])}: {message['content']}"
        for message in messages
    )


def _flatten_system(system: list[dict[str, Any]]) -> str:
    """The cache-ordered blocks, back into the one string the gateway takes.

    The blocks exist for a breakpoint the gateway has no way to express, so
    here they are simply concatenated in the order they were built. Nothing is
    lost except the caching, which this provider has no way to express.
    """
    return "\n\n".join(block["text"] for block in system)


def _strip_fence(text: str) -> str:
    """Drop a ```json ... ``` wrapper if the model added one.

    Asking for JSON in a prompt gets JSON, but a model that has been told to
    return JSON its whole life will sometimes dress it in a markdown fence.
    The Bedrock and direct providers never need this - they get a real schema
    enforced by the API - so it lives here, with the provider that has to ask
    nicely instead.
    """
    if not text.startswith("```"):
        return text
    body = text.split("\n", 1)[-1] if "\n" in text else ""
    return body.rsplit("```", 1)[0].strip()


def _complete_gateway(
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
    """Claude behind an HTTP endpoint that holds the real credentials for us.

    This is the provider for a deployment that has no AWS identity of its own.
    An API Gateway key opens exactly one POST route, and whatever sits behind
    it - a Lambda, in the case this was written for - is what actually talks to
    Bedrock. Nothing here needs an SDK, an AWS region, or a credential chain,
    which is the entire appeal: it works from any box, including one with no
    instance role.

    Everything except `system` and `messages` is accepted to satisfy the
    provider signature and then ignored, because the far side chooses all of
    it. Those are real limitations, and they are now DECLARED rather than
    worked around in silence - see `GATEWAY_CAPABILITIES` below and the router
    in `brain/__init__.py`. The difference matters: previously this function
    was handed a JSON schema it could not enforce and a conversation it could
    not represent, and the caller had no way to know that what came back was a
    degraded answer rather than a good one.

    What the endpoint does not implement:

    * **No system turn, and no turns at all.** It reads one `prompt` field and
      silently drops the rest. Passing the system prompt as its own key returns
      a cheerful 200 with the character quietly missing - the model answers as
      a generic assistant - so system and messages are folded into one string
      instead, with the conversation rendered as a labelled transcript. That is
      strictly worse than real turns (the model reads its own past answers as
      quoted text rather than as its own voice), and it is the price of an
      endpoint with one field.
    * **No structured output.** There is nowhere to put `output_config.format`,
      so a schema is demoted to an instruction in the prompt and the fence is
      stripped off the answer. Tasks that need a schema to be *enforced* -
      filings, votes, memory rewrites - are no longer routed here at all.
    * **No prompt caching.** No breakpoints to place, so the blocks are simply
      concatenated. Every call pays full price for the shared prefix.
    * **A hard output cap, and no way to raise it.** The far side stops at its
      own limit and ignores `max_tokens`, which in Hebrew - roughly a token per
      character - lands around 450 characters, a third of what the same cap
      buys in English. Short tasks never notice. A filing written at full
      length comes back cut mid-string and fails `json.loads`, so the schema
      instruction below also asks for a length that fits.

    Usage counters come back empty, which is honest: there is nothing to count.
    """
    if not credential.endpoint:
        raise ValueError(
            f"credential {credential.label!r} has no endpoint, which the gateway needs"
        )

    text_prompt = f"{_flatten_system(system)}\n\n{_flatten(messages)}"
    if output_format is not None:
        schema = json.dumps(output_format.get("schema", {}), ensure_ascii=False)
        text_prompt += (
            "\n\n## הפורמט\n"
            "החזר אך ורק אובייקט JSON תקין, בלי טקסט לפני או אחרי ובלי גדר markdown, "
            f"לפי הסכימה הזאת:\n{schema}\n\n"
            "חשוב: כל התשובה יחד חייבת להיות קצרה מ-350 תווים. גוף "
            "התביעה: שני משפטים קצרים לכל היותר. תשובה ארוכה מזה "
            "תיקטע באמצע ותיפסל."
        )

    request = urllib.request.Request(
        credential.endpoint,
        data=json.dumps({"prompt": text_prompt}).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json", "x-api-key": credential.api_key},
    )
    timeout = get_settings().llm_timeout_seconds
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))

    text = ""
    if isinstance(payload, dict):
        for key in _GATEWAY_TEXT_KEYS:
            value = payload.get(key)
            if isinstance(value, str):
                text = value
                break

    text = text.strip()
    return Completion(text=_strip_fence(text) if output_format is not None else text)
