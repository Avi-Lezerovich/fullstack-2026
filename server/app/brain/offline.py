"""The deterministic offline generator - the court stenographer.

No API key, no network, no latency, and the same inputs always produce the same
output. That last property is not a limitation, it is the point:

* the trial engine can retry a crashed tick and reproduce the identical
  comment, so the dedupe key and the text agree;
* tests can assert on real generated output instead of mocking it away;
* the whole application runs and demonstrates fully with nothing configured -
  which is a hard requirement, not a nicety.

The seed is a hash of *all* the inputs, so a different case gives different
text, while the same case gives the same text forever.

--- what this is NOT, deliberately -------------------------------------------

It used to try to be the characters. Each personality carried a `[tone:x]`
marker, and this module drew that tone's phrases from a twelve-bank corpus to
produce something that read like a juror speaking.

It read like a juror speaking for about a day. A phrase bank cannot read the
case in front of it, so what it actually produced was a *register* - the same
nine openings and six shapes, recombined, bolted onto whatever case came next.
The failure mode was not "the fallback is a bit flat". It was that the site
appeared to have twenty personalities who all said the same kind of thing, and
no reader could tell that a fallback was involved at all. Shallow characters
are a far worse outcome than obviously-absent ones.

So this writes **the minute** instead: what was filed, what was heard, what was
decided. Impersonal, clerical, correct, and unmistakably not a person talking.
Nobody reads a docket entry and concludes the judge is boring.

The practical consequence is that nothing here has to be good, so nothing here
has to grow. `tone_of` is gone along with the banks it selected: the offline
path no longer has a notion of who is speaking, because it no longer pretends
to be them.
"""

from __future__ import annotations

import hashlib
import json
import random
import re
from typing import Any

from . import corpus

DEFAULT_MAX_CHARS = 400

_SLOT_RE = re.compile(r"\{([a-z_]+)\}")


class _Blanks(dict):
    """Missing placeholders resolve to nothing rather than raising.

    A template referring to a slot this task has no value for should quietly
    drop it, not crash a juror mid-deliberation.
    """

    def __missing__(self, key: str) -> str:  # pragma: no cover - trivial
        return ""


def slots_in(template: str) -> list[str]:
    return _SLOT_RE.findall(template)


def seed_for(personality_prompt: str, task: str, context: dict[str, Any]) -> int:
    """A stable 64-bit seed derived from every input.

    sort_keys matters: two dicts with the same content must hash identically
    regardless of insertion order, or a retry would produce different text.
    """
    payload = json.dumps(
        {"p": personality_prompt, "t": task, "c": context},
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    )
    digest = hashlib.blake2b(payload.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big")


def _context_values(context: dict[str, Any], rng: random.Random) -> dict[str, str]:
    """Turn a case into the fragments templates can quote.

    This is what makes output visibly about *this* trial: the defendant's name,
    one of its actual charges, a few words of its real title.
    """
    charges = context.get("charges") or []
    title = str(context.get("case_title") or "").strip()
    title_quote = " ".join(title.split()[:6])

    guilty = context.get("tally_guilty")
    not_guilty = context.get("tally_not_guilty")
    tally = f"{guilty} מול {not_guilty}" if guilty is not None and not_guilty is not None else ""

    verdict = context.get("verdict")
    verdict_word = {"guilty": "חייב", "not_guilty": "זכאי"}.get(str(verdict), "")

    return {
        "defendant": str(context.get("defendant") or "הנתבע"),
        "plaintiff": str(context.get("plaintiff") or "התובע"),
        "charge": str(rng.choice(charges)) if charges else "הסעיף שבנדון",
        "title_quote": title_quote or "כתב התביעה",
        "tally": tally,
        "verdict_word": verdict_word,
    }


def _fill(text: str, values: dict[str, str]) -> str:
    """Resolve placeholders, including ones that appear inside phrases.

    Two passes are needed because a phrase drawn from a bank may itself contain
    a context placeholder - "{stance} {evidence}" expands to text still holding
    "{defendant}".
    """
    for _ in range(3):
        if "{" not in text:
            break
        expanded = text.format_map(_Blanks(values))
        if expanded == text:
            break
        text = expanded
    return text


def trim(text: str, max_chars: int) -> str:
    """Cut at a word boundary, and never return an empty string."""
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > max_chars:
        cut = text[:max_chars]
        if " " in cut:
            cut = cut[: cut.rindex(" ")]
        text = cut.rstrip(" ,;:-") + "…"
    return text or "אין לי מה להוסיף."


def generate(
    personality_prompt: str,
    task: str,
    context: dict[str, Any] | None = None,
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> str:
    context = context or {}
    rng = random.Random(seed_for(personality_prompt, task, context))

    templates = corpus.TEMPLATES.get(task)
    if not templates:
        # An unknown task is a programming error, but a juror going silent
        # mid-trial is worse than a generic line.
        return trim(context.get("fallback") or "אין לי מה להוסיף.", max_chars)

    # The personality still seeds the choice even though it no longer selects a
    # voice: two jurors filing the same minute on the same case should not write
    # a byte-identical line, or the deliberation reads as a copy-paste error
    # rather than as a record of seven people.
    template = rng.choice(templates)
    return trim(_fill(template, _context_values(context, rng)), max_chars)


def invent_lawsuit(
    personality_prompt: str,
    seed_extra: str = "",
    target: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """A whole filing for a bot acting on its own initiative.

    Three kinds of defendant, matching the live model's three briefs:

      thing    - drawn from the fixed corpus list. Never from the user table:
                 a bot must not be able to sue a real person.
      topical  - something about right now, supplied by the caller from the
                 clock (and from TOPICAL_SUBJECTS, if an operator set any).
      bot      - another one of the court's own personalities, by name.

    The bot and topical kinds need no new phrase banks at all: the defendant is
    just a different string flowing into the same {defendant} slot, which is
    the whole reason that slot exists.
    """
    target = target or {"kind": "thing"}
    kind = str(target.get("kind") or "thing")

    # The target is part of the seed, so a filing against a colleague and a
    # filing against a thing are different filings even on the same tick.
    rng = random.Random(
        seed_for(
            personality_prompt,
            "bot_lawsuit_meta",
            {"s": seed_extra, "k": kind, "n": target.get("name") or ""},
        )
    )

    if kind == "bot" and target.get("name"):
        defendant = str(target["name"])
    elif kind == "topical" and target.get("subjects"):
        defendant = str(rng.choice(list(target["subjects"])))
    else:
        defendant = rng.choice(corpus.LAWSUIT_DEFENDANTS)

    charges = rng.sample(corpus.LAWSUIT_CHARGES, k=rng.randint(1, 3))
    title = rng.choice(corpus.LAWSUIT_TITLES).format(defendant=defendant)

    # `case_title` is deliberately NOT passed down. It feeds the {title_quote}
    # slot, and since the title is itself built from the defendant, the body
    # came out quoting its own headline back at the reader - "מוגשת בזאת תביעה
    # נגד ההודעה שנשלחה בטעות. הביטוי התביעה נגד ההודעה שנשלחה בטעות כשלעצמו
    # מעיד על חומרת המקרה." Without it the {title_quote} phrases fall back to
    # the generic "כתב התביעה", which reads like a filing instead of an echo.
    body = generate(
        personality_prompt,
        "bot_lawsuit",
        {"defendant": defendant, "charges": charges},
        max_chars=600,
    )
    return {"title": title, "defendant_text": defendant, "charges": charges, "body": body}
