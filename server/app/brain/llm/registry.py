"""The provider table: what backends exist, and which credential can use which."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from ...config import get_settings
from .providers.base import Completion, _complete_anthropic, _complete_bedrock
from .providers.gateway import _complete_gateway
from .providers.gemini import _complete_gemini


@dataclass(frozen=True)
class Capabilities:
    """What a backend can actually do, as opposed to what it is asked to do.

    This exists because of one specific bug shape. The gateway provider has
    never supported structured output; it was nevertheless handed a JSON schema
    and asked for a lawsuit. It answered - plausibly, in Hebrew, with a fence
    around it and sometimes cut off mid-string - and every layer above treated
    that as an ordinary result. When it parsed, a schema that was supposed to
    be *enforced* had merely been *suggested*; when it did not, the failure was
    logged as though the model had misbehaved rather than as a provider that
    was never able to comply.

    Declaring the limit lets `brain` route around it and say what was missing,
    so a degraded backend looks degraded instead of looking like a bad model.

    Only the limits something BRANCHES on live here. An earlier version also
    carried `system_turn` and `caching` flags, which were true statements that
    nothing ever read: the gateway degrades on both without needing to be
    asked, because folding turns into a transcript and ignoring a cache
    breakpoint both produce a correct answer, just a worse or dearer one. A
    field that only ever gets asserted in its own test is documentation
    pretending to be a mechanism - the gateway's docstring above says all three
    limits in prose, where they belong.
    """

    # A schema the API enforces. Without it there is no such thing as a
    # guaranteed-parseable answer, so no vote and no filing - and "the model
    # returned something plausible" is not a substitute, because the rule that
    # a bot may never sue a person is checked against exactly such a field.
    structured_output: bool = True


SDK_CAPABILITIES = Capabilities()
GATEWAY_CAPABILITIES = Capabilities(structured_output=False)


@dataclass(frozen=True)
class Provider:
    """One backend: how to call it, when it is usable, what it runs by default."""

    complete: Callable[..., Completion]
    # Given a Credential, is this provider credentialed enough to be worth
    # trying?
    # Cheap and local - a real check would mean a network round trip on every
    # health poll. Anything it cannot see (a missing SDK, an expired role, a
    # revoked key) surfaces as a failed call, falls back like any other error,
    # and is reported by /api/health via brain.LAST_CALL.
    is_configured: Callable[[Any], bool]
    # Bedrock namespaces its model ids; the direct API does not.
    default_model: str
    capabilities: Capabilities = field(default_factory=Capabilities)


PROVIDERS: dict[str, Provider] = {
    "bedrock": Provider(
        complete=_complete_bedrock,
        is_configured=lambda credential: bool(credential.aws_region),
        default_model="anthropic.claude-opus-5",
        capabilities=SDK_CAPABILITIES,
    ),
    "anthropic": Provider(
        complete=_complete_anthropic,
        is_configured=lambda credential: bool(credential.api_key),
        default_model="claude-opus-5",
        capabilities=SDK_CAPABILITIES,
    ),
    "gemini": Provider(
        complete=_complete_gemini,
        # One key, one host - Google needs no region and no endpoint of its own.
        is_configured=lambda credential: bool(credential.api_key),
        # VERIFY THIS AGAINST YOUR OWN KEY BEFORE TRUSTING IT. Google's model
        # availability differs per account: a measurement taken against this
        # project on 2026-09-01 had every 2.5-series model answering 404 "no
        # longer available to new users", while the published free-tier figures
        # below describe models that account could not reach. The admin AI
        # tab's failure panel now shows Google's own message, so one call
        # settles it - and a 404 here is a 100% failure rate, not a slow day.
        #
        # Flash-Lite, not the newest Flash. The point of this provider is a
        # real schema on a free tier, and the free tier is not uniform across
        # models: Google publishes ~1,000 requests a day for 2.5 Flash-Lite
        # and publishes nothing at all for the current-generation Flash
        # models, whose measured allowance is around twenty. This provider was
        # previously defaulted to `gemini-3.7-flash` on the strength of a
        # "roughly 1,500 a day" figure that belongs to a different model, and
        # the court spent its whole daily allowance before anyone was awake.
        #
        # Flash-Lite is also the right answer on the merits and not only on
        # price: the tasks routed here are a juror's one-line vote, a filing
        # and a memory rewrite, none of which is reasoning-heavy, and it is
        # the fastest model in the family. Should this ever move to a paid
        # tier it is $0.10/$0.40 per million tokens - a rounding error at this
        # site's volume.
        default_model="gemini-2.5-flash-lite",
        capabilities=SDK_CAPABILITIES,
    ),
    "gateway": Provider(
        complete=_complete_gateway,
        # Both halves matter: the key alone cannot say where to send itself.
        is_configured=lambda credential: bool(
            credential.api_key and credential.endpoint
        ),
        # The endpoint picks the model, so there is no default to name here.
        default_model="",
        capabilities=GATEWAY_CAPABILITIES,
    ),
}


def usable(credential: Any) -> bool:
    """Whether this one credential names a provider and has what it needs."""
    provider = PROVIDERS.get(credential.provider)
    return provider is not None and provider.is_configured(credential)


def is_configured(settings: Any) -> bool:
    """Whether ANY credential in the chain is worth trying at all.

    Any, not all: a chain whose third entry is missing its key is a chain of
    two, not a broken deployment. The missing one is reported through
    `Settings.llm_credential_errors` and by never being selected.
    """
    return any(usable(credential) for credential in settings.llm_chain)


def capabilities() -> Capabilities:
    """What the chain can do - the UNION over its usable credentials.

    The union, not the first entry's answer, because `brain` reads this to
    decide whether a task is possible at all ("can I get an enforced enum
    anywhere?") and then the chain filters to the credentials that can
    actually deliver it. Answering with the first credential's capabilities
    would let one gateway entry sitting anywhere in the chain silently
    disable every filing on the site.

    Never raises: this is read on paths that only want to decide whether to
    attempt something, and "no" is a complete answer for a misconfigured
    chain. The call itself still raises loudly when it is actually made.
    """
    return Capabilities(
        structured_output=any(
            PROVIDERS[credential.provider].capabilities.structured_output
            for credential in get_settings().llm_chain
            if usable(credential)
        )
    )


def resolve(credential: Any) -> tuple[Provider, str]:
    """The provider that serves this credential, and the model to ask for."""
    provider = PROVIDERS.get(credential.provider)
    if provider is None:
        raise ValueError(
            f"credential {credential.label!r} names unknown provider "
            f"{credential.provider!r}; known: {', '.join(sorted(PROVIDERS))}"
        )
    return provider, (credential.model or provider.default_model)
