"""The two SDK-backed providers - Bedrock and the direct Anthropic API.

Both speak the first-party Messages API surface, so everything past
construction (`_complete_sdk`) lives once, here, rather than twice.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ....config import get_settings
from ..prompt import _text_of, _THINKING


@dataclass(frozen=True)
class Completion:
    """What one call to a provider produced, and what it cost.

    The usage counters are not bookkeeping for its own sake: prompt caching
    fails *silently* - the requests keep succeeding and the bill is just higher
    - so the only ground truth that the cache is working is
    `cache_read_input_tokens`, and the only way it stays working is for
    something to keep watching it. These flow up into brain.LAST_CALL and out
    through /api/health.
    """

    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read: int = 0
    cache_write: int = 0
    # Which credential and model actually answered, stamped by the chain after
    # the call rather than by the provider - the provider functions stay
    # ignorant of the chain, which is what keeps adding one a single entry in
    # PROVIDERS. Defaulted so every existing construction site still compiles.
    credential: str = ""
    model: str = ""
    latency_ms: int = 0


def _usage_of(message: Any, text: str) -> Completion:
    usage = getattr(message, "usage", None)
    return Completion(
        text=text,
        input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
        output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
        cache_read=int(getattr(usage, "cache_read_input_tokens", 0) or 0),
        cache_write=int(getattr(usage, "cache_creation_input_tokens", 0) or 0),
    )


def _output_config(effort: str, output_format: dict[str, Any] | None) -> dict[str, Any]:
    """`effort` always, `format` only when a task needs parseable output."""
    config: dict[str, Any] = {"effort": effort}
    if output_format is not None:
        config["format"] = output_format
    return config


def _complete_sdk(
    client: Any,
    system: list[dict[str, Any]],
    messages: list[dict[str, str]],
    *,
    model: str,
    max_tokens: int,
    effort: str,
    output_format: dict[str, Any] | None,
    stream: bool,
) -> Completion:
    """One Messages request, for any client with the first-party surface.

    Bedrock's Mantle client and the direct client differ only in construction,
    so everything after that lives here rather than twice.

    `stream` is not about showing anything to anybody - nothing here is
    rendered token by token. It is there because the SDK's HTTP timeout applies
    to the whole non-streaming request, and a filing asks for enough tokens
    that a slow generation can trip it. Streaming and taking the final message
    gets the same object without the ceiling.
    """
    kwargs: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "thinking": _THINKING,
        "output_config": _output_config(effort, output_format),
        "system": system,
        "messages": messages,
    }
    if stream:
        with client.messages.stream(**kwargs) as response:
            message = response.get_final_message()
    else:
        message = client.messages.create(**kwargs)
    return _usage_of(message, _text_of(message))


def _complete_bedrock(system, messages, *, credential, **kwargs: Any) -> Completion:
    """Claude on Amazon Bedrock, via the SDK's Mantle (Messages API) client.

    Credentials come from the standard AWS chain - AWS_ACCESS_KEY_ID and
    friends, a shared profile named by AWS_PROFILE, or the EC2/ECS role - and
    never from an API key. Region is the one thing the client will not infer,
    which is why the region is what gates this provider.
    """
    from anthropic import AnthropicBedrockMantle

    client = AnthropicBedrockMantle(
        aws_region=credential.aws_region,
        timeout=get_settings().llm_timeout_seconds,
        max_retries=1,
    )
    return _complete_sdk(client, system, messages, **kwargs)


def _complete_anthropic(system, messages, *, credential, **kwargs: Any) -> Completion:
    """Claude on the direct Anthropic API, keyed by this credential's key."""
    import anthropic

    client = anthropic.Anthropic(
        api_key=credential.api_key,
        timeout=get_settings().llm_timeout_seconds,
        max_retries=1,
    )
    return _complete_sdk(client, system, messages, **kwargs)
