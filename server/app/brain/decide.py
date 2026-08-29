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


# What an idle bot does when it is not serving on a jury. Weighted so the feed
# gains a steady trickle of activity without being buried in bot lawsuits.
SOCIAL_ACTIONS = (("like", 0.60), ("comment", 0.25), ("file_case", 0.15))


def decide_bot_action(*, agent_user_id: int, tick: int, salt: str = "") -> str:
    """Which idle social action this bot takes on this tick."""
    return _weighted(_rng(salt, "social", agent_user_id, tick), SOCIAL_ACTIONS)


# Who a bot sues when it files on its own initiative.
#
#   thing    - an everyday object or situation, from the fixed corpus list.
#              Still the majority, because it is the core joke of the site.
#   topical  - something about right now: the season, the day, the hour, or a
#              subject an operator put in TOPICAL_SUBJECTS.
#   bot      - another one of the court's own personalities. A feud between two
#              regulars is the best thing the feed can produce, but it stops
#              being funny if it is most of what the feed produces.
#
# Never a human. That is not a weight, it is a rule enforced separately - in
# the worker, against the database - because a bot suing a real user would be
# harassment with a court date attached.
LAWSUIT_TARGETS = (("thing", 0.50), ("topical", 0.30), ("bot", 0.20))


def decide_lawsuit_target(*, agent_user_id: int, tick: int, salt: str = "") -> str:
    """What kind of defendant this filing goes after.

    Seeded by the same (bot, tick) pair as the action itself, so a retried tick
    files the same lawsuit against the same kind of target rather than quietly
    producing a second, different case.
    """
    return _weighted(_rng(salt, "target", agent_user_id, tick), LAWSUIT_TARGETS)


def _weighted(rng: random.Random, options: tuple[tuple[str, float], ...]) -> str:
    roll = rng.random()
    cumulative = 0.0
    for value, weight in options:
        cumulative += weight
        if roll < cumulative:
            return value
    return options[-1][0]  # pragma: no cover - float rounding guard
