"""Content scanning - a weighted lexicon, deliberately not an LLM.

This runs on the publish path, in the same transaction as the INSERT, so it has
to be fast and it has to be deterministic. A model call here would add latency
to every comment and make the moderation tests depend on generated text.

The lexicon is tuned for the fact that this is a *complaints* app. The whole
premise is people writing furiously about Mondays, so ordinary negative words
carry no weight at all - only genuine abuse directed at a person does.
Flagging "the service was terrible" would flag the entire site.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

TOXIC_THRESHOLD = 0.70
BORDERLINE_THRESHOLD = 0.35

# Abuse aimed at a person, and threats. These are the only things that matter.
SEVERE_TERMS: dict[str, float] = {
    "מטומטם": 0.75,
    "מטומטמת": 0.75,
    "אידיוט": 0.75,
    "אידיוטית": 0.75,
    "מפגר": 0.85,
    "מפגרת": 0.85,
    "תמות": 0.90,
    "שתמות": 0.90,
    "אני אהרוג": 0.95,
    "מגיע לך למות": 0.95,
    "זבל": 0.55,
    "חרא": 0.55,
    "idiot": 0.75,
    "moron": 0.75,
    "kill yourself": 0.95,
}

# Hostile, but not automatically disqualifying.
#
# The weights encode a judgement specific to this app: calling the defendant a
# liar is ordinary legal argument and stays publishable on its own, whereas
# calling a person an animal is borderline by itself. Either way, a pile of
# these accumulates past the toxic threshold.
MODERATE_TERMS: dict[str, float] = {
    "שונא אותך": 0.45,
    "בהמה": 0.40,
    "מגעיל": 0.35,
    "טיפש": 0.30,
    "טיפשה": 0.30,
    "שקרן": 0.25,
    "שקרנית": 0.25,
    "דוחה": 0.25,
    "נבזה": 0.25,
    "disgusting": 0.35,
    "liar": 0.25,
}

ALL_TERMS: dict[str, float] = {**SEVERE_TERMS, **MODERATE_TERMS}

# Word-boundary matching so "זבל" does not fire inside a longer, innocent word.
# Hebrew letters are word characters to Python's re, so \b behaves correctly.
_PATTERNS: list[tuple[str, float, re.Pattern[str]]] = [
    (term, weight, re.compile(rf"\b{re.escape(term)}\b", re.IGNORECASE | re.UNICODE))
    for term, weight in ALL_TERMS.items()
]


@dataclass(frozen=True)
class Scan:
    label: str  # ok | borderline | toxic
    score: float
    terms: tuple[str, ...]

    @property
    def matched_terms(self) -> str:
        """Comma-separated, for the moderation_scans row."""
        return ", ".join(self.terms)[:255]


def scan(text: str) -> Scan:
    """Score a piece of content and classify it.

    Weights accumulate, so a single mild insult stays publishable while a pile
    of them does not. The score is capped at 1.0 so one very long abusive
    message is not treated as infinitely worse than a short one.
    """
    if not text:
        return Scan(label="ok", score=0.0, terms=())

    matched: list[str] = []
    total = 0.0
    for term, weight, pattern in _PATTERNS:
        if pattern.search(text):
            matched.append(term)
            total += weight

    score = round(min(1.0, total), 3)
    if score >= TOXIC_THRESHOLD:
        label = "toxic"
    elif score >= BORDERLINE_THRESHOLD:
        label = "borderline"
    else:
        label = "ok"

    return Scan(label=label, score=score, terms=tuple(matched))


def status_for(label: str) -> str:
    """The moderation_status a scan result implies at publish time.

    'flagged' is still publicly visible - borderline content stays up, marked
    for review, rather than being silently removed.
    """
    return {"toxic": "rejected", "borderline": "flagged"}.get(label, "published")
