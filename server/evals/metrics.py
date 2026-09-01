# -*- coding: utf-8 -*-
"""The four measures, and the one of them that needs no model.

Kept apart from `run.py` so each can be read on its own terms: what is being
counted, and why that number means what it claims to mean.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from typing import Any

from app.brain import llm

# Hebrew word tokens. Deliberately crude - no stemming, no stopword list - so
# that the repetition number counts the surface the reader actually sees. A
# stemmer would forgive exactly the repetition this is looking for.
_WORD = re.compile(r"[֐-׿']+")


def tokens(text: str) -> list[str]:
    return _WORD.findall(text or "")


def distinct_n(texts: list[str], n: int = 2) -> float:
    """Unique n-grams as a fraction of all n-grams, across a set of outputs.

    The standard diversity measure, and the one that catches "canned" without
    anybody having to read a hundred lines. A phrase bank scores low here by
    construction: it recombines a fixed pool, so the same bigrams recur however
    many outputs you sample. A voice with real range scores high and stays high
    as the sample grows.

    1.0 means nothing repeated; 0.1 means the same ten phrases over and over.
    """
    grams: Counter[tuple[str, ...]] = Counter()
    for text in texts:
        words = tokens(text)
        grams.update(tuple(words[i : i + n]) for i in range(len(words) - n + 1))
    total = sum(grams.values())
    return round(len(grams) / total, 4) if total else 0.0


def self_overlap(texts: list[str], n: int = 3) -> float:
    """How much ONE character repeats ITSELF across its own outputs.

    Different question from `distinct_n`, and the more diagnostic of the two.
    A cast can look varied in aggregate while every individual member says the
    same three things - which is precisely what an exemplar-free character
    sheet produces, and precisely what a reader following one judge notices
    first.

    0.0 is ideal. Above ~0.2 the character has a catchphrase problem.
    """
    seen: set[tuple[str, ...]] = set()
    repeats = total = 0
    for text in texts:
        words = tokens(text)
        for i in range(len(words) - n + 1):
            gram = tuple(words[i : i + n])
            total += 1
            if gram in seen:
                repeats += 1
            seen.add(gram)
    return round(repeats / total, 4) if total else 0.0


# --- the judged measures -----------------------------------------------------
#
# These ask a model. That is a real cost and a real source of noise, so each one
# is a question with a right answer rather than a rating out of ten: "which of
# these five wrote it" and "is this claim in the text" are both checkable, and
# neither inherits the length and position biases that make a 1-5 quality score
# unreliable.

_ATTRIBUTION_SCHEMA: dict[str, Any] = {
    "type": "json_schema",
    "schema": {
        "type": "object",
        "properties": {
            "choice": {
                "type": "integer",
                "description": "מספר הדמות שכתבה את השורה, לפי הרשימה",
            }
        },
        "required": ["choice"],
        "additionalProperties": False,
    },
}

_GROUNDED_SCHEMA: dict[str, Any] = {
    "type": "json_schema",
    "schema": {
        "type": "object",
        "properties": {
            "invented": {
                "type": "boolean",
                "description": "האם הטקסט טוען עובדה על התיק שלא מופיעה בחומר",
            },
            "what": {"type": "string", "description": "העובדה שהומצאה, אם יש"},
        },
        "required": ["invented", "what"],
        "additionalProperties": False,
    },
}

JUDGE_SYSTEM = (
    "אתה בודק איכות של מערכת דמויות. אתה לא דמות, אתה לא מצחיק, ואתה לא "
    "מנסח יפה. אתה עונה על שאלה אחת, בדיוק, לפי מה שכתוב לפניך ולא לפי מה "
    "שסביר שיהיה נכון."
)


def _judge(prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
    """One question to the judge. Raises; the runner counts what got through."""
    from app.config import get_settings

    settings = get_settings()
    provider, model = llm._provider_and_model(settings)
    raw = provider.complete(
        [{"type": "text", "text": JUDGE_SYSTEM}],
        [{"role": "user", "content": prompt}],
        model=model,
        max_tokens=1024,
        # The judge gets more room to think than the characters do. It is
        # answering a discrimination question over five long character sheets,
        # which is genuinely harder than writing one line in character.
        effort="medium",
        output_format=schema,
        stream=False,
    )
    return json.loads(raw.text)


def attribute(line: str, sheets: list[str]) -> int:
    """Which of `sheets` wrote `line`, as a 0-based index. -1 if unparseable.

    This is the voice-consistency measure, and it needs no labelled data: the
    right answer is known by construction, because the harness generated the
    line. Accuracy against chance (1/len(sheets)) is the whole number.

    It is a much better proxy for "does this character sound like itself" than
    a rating, because it measures the thing a reader actually does - telling
    two personalities apart - rather than an opinion about quality.
    """
    listing = "\n\n".join(
        f"### דמות {i + 1}\n{sheet.strip()}" for i, sheet in enumerate(sheets)
    )
    answer = _judge(
        "לפניך חמש דמויות של בית משפט סאטירי, ואחריהן שורה אחת שאחת מהן "
        f"אמרה באולם.\n\n{listing}\n\n### השורה\n{line}\n\n"
        "איזו דמות אמרה אותה? החזר את המספר שלה בלבד.",
        _ATTRIBUTION_SCHEMA,
    )
    return int(answer.get("choice", 0)) - 1


def is_grounded(line: str, context: dict[str, Any]) -> tuple[bool, str]:
    """Whether `line` invents a fact about the case that is not in `context`.

    The failure this catches is specific and was real: a bot given only a case
    title wrote a confident comment about a story it made up, because a title
    and a name is all it had. Colour, opinion and invented legal precedent are
    all fine here - they are the house style. A claim about what happened is
    not.
    """
    facts = "\n".join(
        f"- {key}: {value}" for key, value in context.items() if value not in (None, "", [])
    )
    answer = _judge(
        f"### מה ידוע על התיק\n{facts}\n\n### מה נאמר באולם\n{line}\n\n"
        "האם הטקסט טוען עובדה על התיק שאינה מופיעה למעלה? "
        "דעה, הגזמה, דימוי, או תקדים משפטי מומצא - אינם עובדה על התיק.",
        _GROUNDED_SCHEMA,
    )
    return (not bool(answer.get("invented")), str(answer.get("what") or ""))
