"""The bots' decisions when nothing else can make them.

`decide_vote` was once how EVERY juror voted, and the reasoning was sound as
far as it went: a vote is a value the engine stores, tallies and turns into a
verdict, and parsing one out of generated prose would make the tally depend on
text generation and break the moment a juror phrased itself unusually.

What that argument missed is that the prose was then written *beside* the
decision and never shown it. A juror could deliver a devastating case for
acquittal and be counted as convicting - the argument in the room and the
number in the tally were two unrelated events that happened to concern the same
trial. On a site whose entire premise is characters with opinions, that is not
a rounding error.

So a juror with a model decides for itself, through `brain.deliberate`, which
returns the vote and the line from one structured call. The vote is a
schema-enforced enum, so it is exactly as parseable as the roll below - this is
still not "parsing a decision out of prose" - and it cannot disagree with the
argument, because the same turn wrote both.

**This module is what decides when that is not available**: no credentials, a
provider that cannot enforce a schema, or a failed call. There, `guilt_bias` is
the only thing deciding anything, the choice is a pure seeded function, and
`brain.deliberate` passes the result INTO the prose so the two still agree.

`decide_bot_action` and `decide_lawsuit_target` are unchanged and unconditional.
They pick what a bot does with its turn, not what it thinks - there is nothing
for a model to add, and a model call per idle tick would cost real money to
answer a question a weighted roll answers perfectly.
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
