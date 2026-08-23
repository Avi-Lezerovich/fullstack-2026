"""The bots' decisions - deliberately NOT generated text.

A juror's vote is a value the trial engine stores, tallies and turns into a
verdict. Parsing it out of generated prose would make the tally tests depend on
text generation, and would break the moment a juror phrased itself unusually.

So the decision is a pure, seeded function and the prose is written separately
around it. Both are reproducible from the same inputs, so they never disagree.
"""

from __future__ import annotations

import hashlib
import random
from typing import Any

GUILTY = "guilty"
NOT_GUILTY = "not_guilty"

# How much the evidence can move a juror away from their disposition. Capped so
# a personality still recognisably behaves like itself: the bleeding heart
# should rarely convict even in a damning case.
MAX_EVIDENCE_SWING = 0.20


def _rng(*parts: Any) -> random.Random:
    """A generator seeded by the given parts, stable across processes.

    Python's hash() is randomised per process, so it cannot be used here - the
    web process and the worker must reach identical conclusions.
    """
    key = "|".join(str(part) for part in parts)
    digest = hashlib.blake2b(key.encode("utf-8"), digest_size=8).digest()
    return random.Random(int.from_bytes(digest, "big"))


def evidence_pressure(context: dict[str, Any]) -> float:
    """How much the case itself pushes toward conviction, in [-1, 1].

    Charges and testimony against the defendant push up; testimony for them
    pushes back.
    """
    charges = len(context.get("charges") or [])
    against = int(context.get("testimony_against") or 0)
    supporting = int(context.get("testimony_for") or 0)

    score = 0.12 * min(charges, 5) + 0.15 * min(against, 3) - 0.15 * min(supporting, 3)
    return max(-1.0, min(1.0, score))


def decide_vote(
    *,
    guilt_bias: float,
    case_id: int,
    juror_user_id: int,
    salt: str = "",
    context: dict[str, Any] | None = None,
) -> str:
    """One juror's vote. Pure, and identical every time for a given pairing.

    That reproducibility matters operationally: if the worker crashes after
    writing a juror's comment but before recording the vote, the retry reaches
    the same verdict rather than quietly changing the trial.
    """
    context = context or {}
    swing = evidence_pressure(context) * MAX_EVIDENCE_SWING
    threshold = max(0.02, min(0.98, float(guilt_bias) + swing))

    rng = _rng(salt, "vote", case_id, juror_user_id)
    return GUILTY if rng.random() < threshold else NOT_GUILTY


def decide_sentence_severity(
    *, case_id: int, judge_user_id: int, guilty_votes: int, salt: str = ""
) -> str:
    """How harsh the invented punishment should read.

    A near-unanimous jury gets a harsher sentence, which makes the tally
    visible in the outcome rather than buried in the panel table.
    """
    if guilty_votes >= 6:
        return "harsh"
    if guilty_votes <= 4:
        return "light"
    rng = _rng(salt, "severity", case_id, judge_user_id)
    return rng.choice(["light", "medium", "harsh"])


# What an idle bot does when it is not serving on a jury. Weighted so the feed
# gains a steady trickle of activity without being buried in bot lawsuits.
SOCIAL_ACTIONS = (("like", 0.60), ("comment", 0.25), ("file_case", 0.15))


def decide_bot_action(*, agent_user_id: int, tick: int, salt: str = "") -> str:
    """Which idle social action this bot takes on this tick."""
    rng = _rng(salt, "social", agent_user_id, tick)
    roll = rng.random()
    cumulative = 0.0
    for action, weight in SOCIAL_ACTIONS:
        cumulative += weight
        if roll < cumulative:
            return action
    return SOCIAL_ACTIONS[-1][0]  # pragma: no cover - float rounding guard
