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
        social_every_ticks=_int("SOCIAL_EVERY_TICKS", 4),
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
        # Empty means "whatever brain/llm.py defaults this provider to".
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
