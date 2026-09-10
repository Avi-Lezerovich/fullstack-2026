"""Environment -> a frozen Settings object.

`get_settings()` re-reads the environment on every call rather than caching a
module-level singleton. That costs a handful of int() conversions and buys two
things: tests can change a setting (SSE timings, PHASE_MINUTES) with plain
monkeypatching and have it take effect immediately, and there is no way for a
stale copy of the configuration to linger between the web process and the
worker.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Local development reads .env from the repo root. Inside Docker the variables
# are already set by compose, and load_dotenv never overrides an existing value,
# so this is a no-op there.
_REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_REPO_ROOT / ".env")


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    try:
        return int(raw) if raw else default
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    try:
        return float(raw) if raw else default
    except ValueError:
        return default


def _str(name: str, default: str = "") -> str:
    value = os.environ.get(name)
    return default if value is None else value.strip()


def _csv(name: str) -> tuple[str, ...]:
    """A comma-separated list, empty entries dropped."""
    raw = os.environ.get(name, "")
    return tuple(part.strip() for part in raw.split(",") if part.strip())


def _bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


# --- the brain's credentials --------------------------------------------------
#
# One provider used to be one deployment's whole answer, and LLM_PROVIDER plus
# LLM_API_KEY said it. That stops being enough the moment there is more than one
# key to try, so a credential becomes a value rather than a reading of the
# environment, and the chain is an ordered tuple of them.
#
# Read the quota note in docs/brain.md before assuming a second key helps:
# Google's free tier is per Google Cloud PROJECT, not per API key, so two keys
# minted in one project share one allowance and buy exactly nothing. Distinct
# projects have distinct allowances - but Google's terms forbid creating or
# rotating projects to evade a quota, so the credentials in this chain should
# be ones that exist for their own reasons (a different owner, a different
# vendor, a different billing arrangement), not ones farmed to add up.

# Only these are read; anything else in a record is a typo worth reporting
# rather than silently ignoring.
_CREDENTIAL_FIELDS = frozenset(
    {"provider", "label", "key", "key_env", "model", "endpoint", "region", "cap", "rpm"}
)

_LABEL_MAX = 48  # brain_calls.credential


@dataclass(frozen=True)
class Credential:
    """One way to reach a model: who, with what key, as which model.

    `label` is what the usage dashboard groups by and what `brain_calls`
    stores, so it names the KEY and not the vendor - 'api1-gemini', not
    'gemini'. Two keys for the same provider are two credentials and must be
    two labels, or the board cannot tell you which one is exhausted.

    `daily_cap` is a budget this side of the wire, not a limit Google enforces
    on our say-so. Zero means "no cap known", which is honest for a paid
    account and never blocks a call.

    `rpm` is the same idea on a one-minute window rather than a one-day one -
    see `chain.py`'s module docstring for why a free tier needs both. Zero
    means unpaced, same convention as `daily_cap`.
    """

    label: str
    provider: str
    api_key: str = ""
    model: str = ""
    endpoint: str = ""
    aws_region: str = ""
    daily_cap: int = 0
    rpm: int = 0


def _credential_record(raw: str, position: int) -> tuple[Credential | None, str]:
    """One `key=value,key=value` record. Returns (credential, error)."""
    fields: dict[str, str] = {}
    for pair in raw.split(","):
        pair = pair.strip()
        if not pair:
            continue
        name, _, value = pair.partition("=")
        name = name.strip().lower()
        if name not in _CREDENTIAL_FIELDS:
            return None, f"credential {position}: unknown field {name!r}"
        fields[name] = value.strip()

    provider = fields.get("provider", "")
    if not provider:
        return None, f"credential {position}: no provider"

    label = fields.get("label") or f"api{position}-{provider}"
    if len(label) > _LABEL_MAX:
        return None, f"credential {position}: label longer than {_LABEL_MAX} characters"

    # `key_env` names the variable holding the secret; `key` inlines it. The
    # indirection is the point of the format: it keeps live credentials out of
    # LLM_CREDENTIALS, which is a value this application logs, shows on an
    # admin page, and would otherwise have to redact everywhere.
    api_key = fields.get("key", "")
    if not api_key and fields.get("key_env"):
        api_key = os.environ.get(fields["key_env"], "").strip()

    try:
        cap = max(0, int(fields.get("cap") or 0))
    except ValueError:
        return None, f"credential {position}: cap {fields.get('cap')!r} is not a number"

    try:
        rpm = max(0, int(fields.get("rpm") or 0))
    except ValueError:
        return None, f"credential {position}: rpm {fields.get('rpm')!r} is not a number"

    return (
        Credential(
            label=label,
            provider=provider,
            api_key=api_key,
            model=fields.get("model", ""),
            endpoint=fields.get("endpoint", ""),
            aws_region=fields.get("region", ""),
            daily_cap=cap,
            rpm=rpm,
        ),
        "",
    )


def _parse_credentials(raw: str) -> tuple[tuple[Credential, ...], tuple[str, ...]]:
    """`LLM_CREDENTIALS` -> (credentials in chain order, errors).

    Errors are RETURNED, never raised. `get_settings()` runs on every database
    connection, so a typo that raised here would take the site down rather than
    the brain, and one that was merely logged would scroll past. They surface
    on /api/health instead, where a misconfiguration can look like one.
    """
    credentials: list[Credential] = []
    errors: list[str] = []
    seen: set[str] = set()

    for position, record in enumerate(raw.split(";"), start=1):
        if not record.strip():
            continue
        credential, error = _credential_record(record, position)
        if credential is None:
            errors.append(error)
            continue
        if credential.label in seen:
            errors.append(f"credential {position}: duplicate label {credential.label!r}")
            continue
        seen.add(credential.label)
        credentials.append(credential)

    return tuple(credentials), tuple(errors)


@dataclass(frozen=True)
class Settings:
    # --- database ---
    db_host: str
    db_port: int
    db_user: str
    db_password: str
    db_name: str

    # --- web ---
    port: int
    client_origin: str
    session_secure: bool
    session_ttl_days: int
    reset_ttl_minutes: int
    reset_cooldown_seconds: int
    bcrypt_rounds: int

    # --- trial timing ---
    phase_minutes: int
    tick_seconds: int
    sweep_every_ticks: int
    social_every_ticks: int
    housekeeping_every_ticks: int
    bot_cooldown_minutes: int
    jury_seed_salt: str
    repeat_offender_threshold: int

    # --- server-sent events ---
    sse_poll_seconds: float
    sse_max_seconds: float
    sse_max_streams: int

    # --- the bots' brain ---
    llm_provider: str
    llm_api_key: str
    llm_endpoint: str
    llm_model: str
    llm_timeout_seconds: int
    aws_region: str
    # The chain, in the order it is tried. Always at least one entry: with
    # LLM_CREDENTIALS unset this is the single credential the legacy LLM_*
    # variables describe, so a deployment that changes nothing behaves exactly
    # as it did.
    llm_credentials: tuple[Credential, ...]
    # Records LLM_CREDENTIALS could not parse. Reported by /api/health rather
    # than raised, because this is read on every database connection.
    llm_credential_errors: tuple[str, ...]
    topical_subjects: tuple[str, ...]
    brain_force_offline: bool
    brain_cache_ttl: str

    # --- uploads ---
    upload_dir: str
    upload_max_bytes: int

    # --- mail ---
    mail_backend: str
    mail_from: str
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    smtp_use_tls: bool

    @property
    def client_origins(self) -> list[str]:
        """Origins allowed to send credentialed requests.

        Both loopback spellings are accepted because a browser treats
        localhost and 127.0.0.1 as different origins, and people type both.
        """
        origins = {self.client_origin}
        if "localhost" in self.client_origin:
            origins.add(self.client_origin.replace("localhost", "127.0.0.1"))
        elif "127.0.0.1" in self.client_origin:
            origins.add(self.client_origin.replace("127.0.0.1", "localhost"))
        return sorted(origins)

    @property
    def use_llm(self) -> bool:
        """True when generate() should try the live model backend first.

        What counts as "credentialed" is the provider's own business - Bedrock
        authenticates through the AWS credential chain and has no API key at
        all - so the answer comes from brain.llm. Imported inside the property
        because that module reads this one.
        """
        if self.brain_force_offline:
            return False
        from .brain import llm

        return llm.is_configured(self)

    @property
    def llm_chain(self) -> tuple[Credential, ...]:
        """The credentials worth trying, in order. Empty when forced offline."""
        return () if self.brain_force_offline else self.llm_credentials


def _credential_chain() -> tuple[Credential, ...]:
    """LLM_CREDENTIALS if it names anything, else the legacy single credential.

    The fallback is not a courtesy. Every existing deployment, every compose
    file and most of the test suite configures the brain with LLM_PROVIDER and
    LLM_API_KEY, and all of them must keep working untouched - so an unset
    LLM_CREDENTIALS means a one-element chain built from exactly those,
    labelled with the provider name. That label choice matters too:
    `brain_calls` rows written before any of this exist with `credential`
    empty and are read back as their provider, so the legacy credential lines
    up with its own history on the dashboard instead of appearing as a new key
    that started today.
    """
    credentials, _ = _parse_credentials(_str("LLM_CREDENTIALS"))
    if credentials:
        return credentials

    provider = _str("LLM_PROVIDER", "bedrock")
    return (
        Credential(
            label=provider,
            provider=provider,
            api_key=_str("LLM_API_KEY"),
            model=_str("LLM_MODEL"),
            endpoint=_str("LLM_ENDPOINT"),
            aws_region=_str("AWS_REGION", "") or _str("AWS_DEFAULT_REGION", ""),
        ),
    )


def get_settings() -> Settings:
    return Settings(
        db_host=_str("DB_HOST", "127.0.0.1"),
        db_port=_int("DB_PORT", 3307),
        db_user=_str("DB_USER", "root"),
        db_password=_str("DB_PASSWORD", "lolsuit-dev"),
        db_name=_str("DB_NAME", "lolsuit"),
        port=_int("PORT", 5002),
        client_origin=_str("CLIENT_ORIGIN", "http://localhost:5174"),
        session_secure=_bool("FLASK_SESSION_SECURE", False),
        session_ttl_days=_int("SESSION_TTL_DAYS", 7),
        reset_ttl_minutes=_int("RESET_TTL_MINUTES", 30),
        # A second reset link inside this window is not sent. Cheap defence
        # against using the endpoint to bomb someone's inbox - and against
        # burning the mail provider's daily quota.
        reset_cooldown_seconds=_int("RESET_COOLDOWN_SECONDS", 60),
        # Only ever lowered by the test suite. Never lower it in a deployment.
        bcrypt_rounds=max(4, _int("BCRYPT_ROUNDS", 12)),
        phase_minutes=_int("PHASE_MINUTES", 1440),
        tick_seconds=_int("TICK_SECONDS", 15),
        sweep_every_ticks=_int("SWEEP_EVERY_TICKS", 4),
        # Every 20th tick - five minutes at the default TICK_SECONDS=15 - and
        # not every 4th. This is a spend dial before it is a pacing one. Each
        # social pass costs one model call for the bot whose turn it is, plus
        # one per pending reply, so a 60-second cadence sets a floor near 1,440
        # calls a day before a single juror deliberates. That is already past
        # the most generous free tier Google publishes for any model, which
        # means a free-tier deployment ran out mid-morning every morning and
        # spent the rest of the day on the offline generator with nothing
        # saying so. Five minutes is roughly 290 a day, which fits inside one
        # free key with room for the trials, and the feed does not read
        # noticeably quieter - the bots are on a 30-minute cooldown each
        # anyway, so the faster tick was mostly re-asking who was available.
        social_every_ticks=_int("SOCIAL_EVERY_TICKS", 20),
        # 240 ticks is an hour at the default TICK_SECONDS=15.
        housekeeping_every_ticks=_int("HOUSEKEEPING_EVERY_TICKS", 240),
        bot_cooldown_minutes=_int("BOT_COOLDOWN_MINUTES", 30),
        jury_seed_salt=_str("JURY_SEED_SALT", "lolsuit-v2"),
        repeat_offender_threshold=_int("REPEAT_OFFENDER_THRESHOLD", 3),
        sse_poll_seconds=_float("SSE_POLL_SECONDS", 2.0),
        sse_max_seconds=_float("SSE_MAX_SECONDS", 300.0),
        sse_max_streams=_int("SSE_MAX_STREAMS", 50),
        llm_provider=_str("LLM_PROVIDER", "bedrock"),
        # The direct Anthropic provider and the gateway both use this; they
        # just send it differently. Bedrock reads the standard AWS credential
        # chain instead and ignores this entirely - a key set here while
        # LLM_PROVIDER=bedrock is not a credential, it is a decoy.
        llm_api_key=_str("LLM_API_KEY", ""),
        # The gateway provider's one endpoint, and the only thing it cannot
        # guess. Unused by the other providers, which know their own URLs.
        llm_endpoint=_str("LLM_ENDPOINT", ""),
        # Empty means "whatever brain/llm/registry.py defaults this provider to".
        llm_model=_str("LLM_MODEL", ""),
        # 60 seconds, not 10.
        #
        # Ten was chosen when the brain sent a one-shot prompt and got a
        # sentence back. Current models think before they answer - adaptive
        # thinking is on, and it should be - and a juror weighing a case
        # regularly runs past ten seconds. Every one of those calls raised a
        # timeout, landed in the `except` in brain/__init__.py, and produced a
        # perfectly plausible clerical line from the offline stenographer
        # instead. Nothing broke; the court just quietly stopped having
        # personalities, on the good path, with credentials configured and
        # /api/health reporting a working backend right up until somebody
        # read the failure counter.
        #
        # The worker can afford to wait: it is not serving a request, and the
        # tick it is inside is a background job by construction.
        llm_timeout_seconds=_int("LLM_TIMEOUT_SECONDS", 60),
        # What the bots are allowed to consider "current". The clock gives
        # them the season and the day for free; this is the seam for
        # anything genuinely in the news, deliberately operator-set rather
        # than scraped: a human decides what the court riffs on, and no
        # named real person can end up as a defendant by accident.
        topical_subjects=_csv("TOPICAL_SUBJECTS"),
        # AWS_DEFAULT_REGION is boto3's spelling; accept either.
        aws_region=_str("AWS_REGION", "") or _str("AWS_DEFAULT_REGION", ""),
        llm_credentials=_credential_chain(),
        llm_credential_errors=_parse_credentials(_str("LLM_CREDENTIALS"))[1],
        brain_force_offline=_bool("BRAIN_FORCE_OFFLINE", False),
        # How long a cached prompt prefix lives. "5m" or "1h", and 5m is right
        # for a court that is doing anything at all: a cache read refreshes the
        # timer for free, so continuous traffic keeps a 5-minute entry warm
        # indefinitely, while the 1-hour entry costs twice as much to write.
        # An hour only pays on a deployment with quiet stretches longer than
        # five minutes - which is a thing to measure on /api/health's cache
        # counters, not to guess at here.
        brain_cache_ttl="1h" if _str("BRAIN_CACHE_TTL", "5m") == "1h" else "5m",
        # Where uploaded images land. A directory rather than object storage
        # because the compose stack mounts a volume over it; on EC2 the same
        # variable can point at a mounted EBS path.
        upload_dir=_str("UPLOAD_DIR", str(_REPO_ROOT / "server" / "uploads")),
        # 5 MB. Enforced in three places, deliberately: nginx rejects the body
        # before it reaches Python, Flask's MAX_CONTENT_LENGTH rejects it
        # before the view runs, and the view checks what it actually received.
        upload_max_bytes=_int("UPLOAD_MAX_BYTES", 5 * 1024 * 1024),
        mail_backend=_str("MAIL_BACKEND", "console"),
        mail_from=_str("MAIL_FROM", "court@lolsuit.local"),
        smtp_host=_str("SMTP_HOST", "localhost"),
        smtp_port=_int("SMTP_PORT", 25),
        smtp_user=_str("SMTP_USER", ""),
        smtp_password=_str("SMTP_PASSWORD", ""),
        smtp_use_tls=_bool("SMTP_USE_TLS", False),
    )
