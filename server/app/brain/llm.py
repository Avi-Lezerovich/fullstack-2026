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
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

from ..config import get_settings

log = logging.getLogger(__name__)

# What each task should produce, in the model's own terms.
TASK_BRIEFS: dict[str, str] = {
    "jury_deliberation": "כתוב את דברי המושבע בדיון: משפט או שניים, בגוף ראשון, בעברית.",
    "verdict": "כתוב את הכרעת השופט: משפט או שניים, בעברית, בנימה חד-משמעית.",
    "sentence": "המצא עונש הומוריסטי, קצר ומדויק, בעברית.",
    "moderation_note": "כתוב הערת פיקוח קצרה ועניינית בעברית.",
    "draft_lawsuit": "כתוב טיוטה קצרה לכתב תביעה סאטירי בעברית.",
    "bot_lawsuit": "כתוב כתב תביעה סאטירי קצר בעברית.",
    "suggest_comment": "הצע תגובה קצרה וקולעת בעברית.",
    "bot_comment": "כתוב תגובה קצרה בעברית, כמו משתמש רגיל ברשת.",
}

SYSTEM_PREAMBLE = (
    "אתה דמות קבועה ב-LolSuit, רשת חברתית סאטירית שבה מוגשות תביעות מצחיקות "
    "ומתנהל עליהן משפט. הישאר תמיד באופי שתואר לך, כתוב בעברית, והיה קצר. "
    "אל תסביר את עצמך ואל תוסיף כותרות - החזר רק את הטקסט עצמו."
)


def build_prompt(task: str, context: dict[str, Any]) -> str:
    brief = TASK_BRIEFS.get(task, "כתוב טקסט קצר ומתאים בעברית.")
    lines = [brief, "", "פרטי התיק:"]
    for key, label in (
        ("case_title", "כותרת"),
        ("defendant", "נתבע"),
        ("plaintiff", "תובע"),
        ("case_body", "כתב התביעה"),
        ("charges", "סעיפי אישום"),
        ("testimonies", "עדויות"),
        ("tally_guilty", "קולות חייב"),
        ("tally_not_guilty", "קולות זכאי"),
        ("verdict", "הכרעה"),
    ):
        value = context.get(key)
        if value in (None, "", [], {}):
            continue
        if isinstance(value, (list, tuple)):
            value = "; ".join(str(item) for item in value)
        lines.append(f"- {label}: {value}")
    return "\n".join(lines)


def _text_of(message: Any) -> str:
    """The text blocks of a Messages response, concatenated."""
    return "".join(
        block.text for block in message.content if getattr(block, "type", "") == "text"
    ).strip()


# Off deliberately, on both providers. These are one-line in-character quips,
# there is nothing to reason about, and on current models thinking tokens come
# out of max_tokens - which is tiny here, so a thinking model could think its
# way to an empty completion on every call.
_NO_THINKING = {"type": "disabled"}


def _complete_bedrock(system: str, prompt: str, *, model: str, max_tokens: int) -> str:
    """Claude on Amazon Bedrock, via the SDK's Mantle (Messages API) client.

    Credentials come from the standard AWS chain - AWS_ACCESS_KEY_ID and
    friends, a shared profile named by AWS_PROFILE, or the EC2/ECS role - and
    never from LLM_API_KEY. Region is the one thing the client will not infer,
    which is why AWS_REGION is what gates this provider.
    """
    from anthropic import AnthropicBedrockMantle

    settings = get_settings()
    client = AnthropicBedrockMantle(
        aws_region=settings.aws_region,
        timeout=settings.llm_timeout_seconds,
        max_retries=1,
    )

    message = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        thinking=_NO_THINKING,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    return _text_of(message)


def _complete_anthropic(system: str, prompt: str, *, model: str, max_tokens: int) -> str:
    """Claude on the direct Anthropic API, keyed by LLM_API_KEY."""
    import anthropic

    settings = get_settings()
    client = anthropic.Anthropic(
        api_key=settings.llm_api_key,
        timeout=settings.llm_timeout_seconds,
        max_retries=1,
    )

    message = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        thinking=_NO_THINKING,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    return _text_of(message)


@dataclass(frozen=True)
class Provider:
    """One backend: how to call it, when it is usable, what it runs by default."""

    complete: Callable[..., str]
    # Given a Settings, is this provider credentialed enough to be worth trying?
    # Cheap and local - a real check would mean a network round trip on every
    # health poll. Anything it cannot see (an expired role, a revoked key)
    # surfaces as a failed call and falls back like any other error.
    is_configured: Callable[[Any], bool]
    # Bedrock namespaces its model ids; the direct API does not.
    default_model: str


PROVIDERS: dict[str, Provider] = {
    "bedrock": Provider(
        complete=_complete_bedrock,
        is_configured=lambda settings: bool(settings.aws_region),
        default_model="anthropic.claude-sonnet-5",
    ),
    "anthropic": Provider(
        complete=_complete_anthropic,
        is_configured=lambda settings: bool(settings.llm_api_key),
        default_model="claude-sonnet-5",
    ),
}


def is_configured(settings: Any) -> bool:
    """Whether the configured provider is set up enough to try at all."""
    provider = PROVIDERS.get(settings.llm_provider)
    return provider is not None and provider.is_configured(settings)


def generate(
    personality_prompt: str,
    task: str,
    context: dict[str, Any],
    *,
    max_chars: int = 400,
) -> str:
    """Ask the configured provider. Raises on any failure; the caller falls back."""
    settings = get_settings()

    name = settings.llm_provider
    provider = PROVIDERS.get(name)
    if provider is None:
        raise ValueError(
            f"unknown LLM_PROVIDER {name!r}; known: {', '.join(sorted(PROVIDERS))}"
        )

    text = provider.complete(
        f"{SYSTEM_PREAMBLE}\n\n{personality_prompt}",
        build_prompt(task, context),
        model=settings.llm_model or provider.default_model,
        # Roughly four characters per token for Hebrew, plus headroom.
        max_tokens=max(64, max_chars // 2),
    )

    if not text:
        # An empty completion is a failure, not a valid answer - falling back
        # gives the user something in character instead of a blank comment.
        raise ValueError(f"empty completion from {name}")

    return text
