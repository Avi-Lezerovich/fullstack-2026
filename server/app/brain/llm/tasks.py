"""The actual jobs `brain/__init__.py` asks the model to do.

Everything here works down `chain.candidates()` until one credential answers,
via `_try_chain` - the one place that knows what a retry across credentials
looks like.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, replace
from typing import Any, Callable

from .. import chain
from .prompt import build_prompt, build_system, effort_for, pick_angle, _max_tokens_for
from .providers.base import Completion

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Attempt:
    """One credential's turn at a call: what it was asked, and how it went."""

    credential: str
    provider: str
    model: str
    ok: bool
    latency_ms: int
    error: str | None = None
    usage: Completion | None = None


class AllCredentialsFailed(Exception):
    """Every credential worth trying was tried, and none answered.

    Carries the attempts so `brain` can write one `brain_calls` row per one -
    a credential that was rate-limited really did spend one of somebody's
    requests, and a log that recorded only the final give-up would under-count
    exactly the calls the cap is meant to be counting.
    """

    def __init__(self, attempts: tuple[Attempt, ...], summary: str) -> None:
        super().__init__(summary)
        self.attempts = attempts


def _try_chain(
    call: Callable[[Any, Any, str], Completion],
    *,
    structured: bool = False,
    max_attempts: int = chain.DEFAULT_MAX_ATTEMPTS,
) -> Completion:
    """Work down the chain until one credential answers.

    A failure advances to the next credential rather than being retried here:
    within-provider retries are `_gemini_post`'s job and only for the statuses
    that mean "busy". Asking the same key twice for a fault it has already
    diagnosed spends a second request to learn the same thing.

    What comes back is stamped with which credential and model produced it, so
    `brain` can persist provenance without the provider functions ever having
    to know a chain exists.
    """
    attempts: list[Attempt] = []
    for credential, provider, model in chain.candidates(
        structured=structured, max_attempts=max_attempts
    ):
        chain.note_attempt(credential)
        started = time.monotonic()
        try:
            completion = call(provider, credential, model)
        except Exception as exc:
            elapsed = int((time.monotonic() - started) * 1000)
            chain.note_failure(credential, exc)
            attempts.append(
                Attempt(
                    credential=credential.label,
                    provider=credential.provider,
                    model=model,
                    ok=False,
                    latency_ms=elapsed,
                    error=f"{type(exc).__name__}: {exc}"[:500],
                )
            )
            log.warning(
                "credential %s failed (%s); trying the next", credential.label, exc
            )
            continue

        elapsed = int((time.monotonic() - started) * 1000)
        chain.note_success(credential)
        return replace(
            completion,
            credential=credential.label,
            model=model,
            latency_ms=elapsed,
        )

    raise AllCredentialsFailed(
        tuple(attempts),
        "; ".join(f"{a.credential}: {a.error}" for a in attempts)
        or f"nothing to try - {chain.unavailable()}",
    )


def generate(
    personality_prompt: str,
    task: str,
    context: dict[str, Any],
    *,
    max_chars: int = 400,
    history: list[dict[str, str]] | None = None,
    max_attempts: int = chain.DEFAULT_MAX_ATTEMPTS,
) -> Completion:
    """Ask the configured provider. Raises on any failure; the caller falls back.

    `history` turns this from a one-shot into a conversation. When it is given,
    the brief and the context move into the **system** prompt as a third,
    uncached block and the messages are the real exchange - the bot's own past
    lines arriving as `assistant` turns, which is what stops it answering as
    though it had never met the person. Without it nothing changes: one user
    turn, exactly as before.

    Putting the brief in the system prompt rather than appending it as a final
    user turn is what keeps the roles alternating, and it is also the honest
    shape: "you are this character, answering a private message, and here is
    what you know" is a standing instruction, not something the human said.

    The situation goes in a **user turn** for every other task, and that is a
    caching decision as much as a modelling one: it leaves the two system
    blocks byte-identical across all 31 personalities and all nine tasks, which
    is the entire shared prefix this application has.
    """
    prompt = build_prompt(task, context, pick_angle(personality_prompt, task, context))

    if history:
        system = build_system(personality_prompt, situation=prompt)
        messages = list(history)
    else:
        system = build_system(personality_prompt)
        messages = [{"role": "user", "content": prompt}]

    def call(provider, credential, model):
        completion = provider.complete(
            system,
            messages,
            credential=credential,
            model=model,
            max_tokens=_max_tokens_for(max_chars),
            effort=effort_for(task),
            output_format=None,
            stream=False,
        )
        if not completion.text:
            # An empty completion is a failure, not a valid answer - and
            # raising here rather than returning it means the next credential
            # gets a turn, instead of the caller falling straight to a blank
            # comment because one provider had a bad moment.
            raise ValueError(f"empty completion from {credential.label}")
        return completion

    return _try_chain(call, max_attempts=max_attempts)


# --- a juror's vote and its reasoning, in one breath --------------------------
#
# The vote used to be a seeded RNG and the prose was written separately around
# it. That bought reproducibility - a retried tick reached the same verdict -
# and it cost the thing the site is actually for: a juror could deliver a
# withering argument for acquittal and be tallied as convicting, because the
# text and the decision never met. `_case_context` did not even tell the juror
# which way it had voted.
#
# One structured call fixes it at the source. `vote` is a schema-enforced enum,
# so it is exactly as parseable as the RNG it replaces - this is NOT "parsing a
# decision out of prose", which is the thing decide.py was right to refuse - and
# the line is written by the same turn that chose the side, so the two cannot
# disagree.
#
# What it costs: the vote is no longer byte-reproducible from (case, juror).
# The engine's idempotency does not depend on that and never did - it rests on
# comments.dedupe_key and the `spoke_at IS NULL` guard, and vote and comment
# commit in one transaction, so a retry either finds the work done or redoes
# all of it. `decide.decide_vote` keeps the reproducible behaviour for the
# offline path, where guilt_bias is still the only thing deciding anything.

DELIBERATION_SCHEMA: dict[str, Any] = {
    "type": "json_schema",
    "schema": {
        "type": "object",
        "properties": {
            "vote": {
                "type": "string",
                "enum": ["guilty", "not_guilty"],
                "description": "ההכרעה שלך: guilty = חייב, not_guilty = זכאי",
            },
            "line": {
                "type": "string",
                "description": (
                    "מה שאתה אומר בקול באולם, בעברית, באופי שלך. "
                    "בלי לומר 'אני מצביע' - הנימוק עצמו מסגיר לאן אתה נוטה."
                ),
            },
        },
        "required": ["vote", "line"],
        "additionalProperties": False,
    },
}

# The juror's disposition, described rather than numeric.
#
# `guilt_bias` is a probability in the database, and handing a model "0.75"
# invites it to perform a number: jurors started announcing their own leanings
# ("אני נוטה להרשיע ב-75 אחוז מהמקרים"), which no person has ever said in a
# courtroom. A phrase describes the same disposition in the register the
# character actually thinks in.
_DISPOSITIONS: tuple[tuple[float, str], ...] = (
    (0.25, "אתה כמעט אף פעם לא מרשיע. צריך ממש הרבה כדי לשכנע אותך."),
    (0.40, "אתה נוטה לזכות. ספק סביר הוא ספק, ואתה מוצא אותו כמעט תמיד."),
    (0.60, "אתה מתלבט באמת. שני הצדדים צריכים לעבוד בשבילך."),
    (0.75, "אתה נוטה להרשיע. מי שהגיע לכאן בדרך כלל עשה משהו."),
    (1.01, "אתה מרשיע כמעט תמיד. חפות היא מצב נדיר בעולם שלך."),
)


def disposition_of(guilt_bias: float) -> str:
    for ceiling, phrase in _DISPOSITIONS:
        if guilt_bias < ceiling:
            return phrase
    return _DISPOSITIONS[-1][1]  # pragma: no cover - the last ceiling is > 1


def deliberate(
    personality_prompt: str, context: dict[str, Any], *, guilt_bias: float
) -> dict[str, Any]:
    """One juror's vote and the line they say out loud. Raises; caller falls back.

    Requires structured output, which is checked by the caller rather than
    here - `brain.deliberate` asks `capabilities()` first and never routes a
    provider that cannot enforce the enum into this function.
    """
    prompt = "\n\n".join(
        (
            build_prompt(
                "jury_deliberation",
                context,
                pick_angle(personality_prompt, "jury_deliberation", context),
            ),
            f"## איך אתה בדרך כלל מכריע\n{disposition_of(float(guilt_bias))}\n\n"
            "זו הנטייה שלך, לא כלל. התיק הזה יכול להזיז אותך ממנה - "
            "וההכרעה שתחזיר חייבת להיות זו שהנימוק שלך מוביל אליה.",
        )
    )

    def call(provider, credential, model):
        completion = provider.complete(
            build_system(personality_prompt),
            [{"role": "user", "content": prompt}],
            credential=credential,
            model=model,
            max_tokens=_max_tokens_for(400),
            effort=effort_for("jury_deliberation"),
            output_format=DELIBERATION_SCHEMA,
            stream=False,
        )
        if not completion.text:
            raise ValueError(f"empty deliberation from {credential.label}")
        return completion

    raw = _try_chain(call, structured=True)

    data = json.loads(raw.text)
    vote = str(data.get("vote") or "")
    line = str(data.get("line") or "").strip()

    # Meaning, not shape. A vote outside the enum would be tallied as neither
    # guilty nor not_guilty and quietly vanish from the count.
    if vote not in ("guilty", "not_guilty") or not line:
        raise ValueError("incomplete deliberation from the model")

    return {"vote": vote, "line": line, "usage": raw}


# --- a whole filing, invented -------------------------------------------------

# `additionalProperties: false` and a full `required` list are what make this a
# schema the API enforces rather than a suggestion - the response is guaranteed
# to parse, so the only validation left below is about *meaning*.
LAWSUIT_SCHEMA: dict[str, Any] = {
    "type": "json_schema",
    "schema": {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "כותרת התביעה בעברית, עד 12 מילים",
            },
            "defendant": {
                "type": "string",
                "description": (
                    "הנתבע - חייב להיות חפץ, מושג, יום בשבוע, תופעה או מצב. "
                    "לעולם לא אדם, לא שם פרטי ולא משתמש."
                ),
            },
            "charges": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
                "maxItems": 3,
                "description": "סעיפי אישום קצרים בעברית, שתיים עד ארבע מילים כל אחד",
            },
            "body": {
                "type": "string",
                "description": "גוף כתב התביעה בעברית, שתיים-שלוש פסקאות קצרות",
            },
        },
        "required": ["title", "defendant", "charges", "body"],
        "additionalProperties": False,
    },
}

# The shared half of every filing brief, whoever the defendant turns out to be.
FILING_BRIEF = """אתה מגיש כתב תביעה חדש משלך, ביוזמתך, כי משהו קטן חצה סוף סוף את הגבול.

תכתוב:
- כותרת בסגנון כתב תביעה
- הנתבע
- סעיפי אישום, בניסוח משפטי-רשמי שנשמע אמיתי לחלוטין
- גוף התביעה: מה קרה, מתי זה חצה את הגבול, ומה אתה דורש מבית המשפט

הכול באופי שלך, ובעברית."""


# And the half that changes with the target. Each one ends up appended to the
# brief above, so the model gets one coherent instruction rather than a list of
# conditions to reconcile.
TARGET_BRIEFS: dict[str, str] = {
    "thing": """**בחר נתבע לא צפוי.** לא "יום שני" ולא "התור בסופר" - אלה נתבעו כאן אלף פעם. תמצא את העוול הקטן והספציפי שרק אתה שמת לב אליו: חפץ, מנהג, צליל, רגע ביום, פיצ'ר בטלפון, כלל לא כתוב שכולם מצייתים לו.

הנתבע חייב להיות **דבר, לא אדם**. לא שם של מישהו, לא משתמש, לא דמות אמיתית.""",
    "topical": """**תבע משהו מהתקופה הזאת ממש.** לא עוול נצחי - עוול של עכשיו: של העונה, של החודש, של היום בשבוע, של השעה.

הנתבע חייב להיות **תופעה, לא אדם**: מזג האוויר, מועד בלוח השנה, מנהג עונתי, מצב שכולם נמצאים בו יחד השבוע. לעולם לא אדם אמיתי, לא ארגון אמיתי ולא שם שמופיע בחדשות - את התופעה תובעים, לא את מי שמאשימים בה.

תכתוב כאילו זה נכתב היום, ומי שיקרא את זה מחר יזהה בדיוק על מה מדובר.""",
    "bot": """**אתה תובע עמית לבית המשפט.** מדובר בדמות קבועה כאן, שאתה מכיר היטב מעשרות דיונים משותפים.

זו לא תביעה עקרונית - זו **תביעה אישית**, והיא הרבה יותר מצחיקה ככל שהיא קטנוניות יותר. משהו שהוא עושה באולם, מילה שהוא חוזר עליה, נימה שנמאס לך ממנה, פעם אחת שהוא הפסיק אותך באמצע ולא התנצל.

תישאר בגבולות בית המשפט: זה ריב בין קולגות, לא השמצה. שנוני, לא אכזרי - ואתם עוד תשבו יחד בהרכב הבא.

**הנתבע חייב להיות בדיוק השם שנמסר לך למטה, מילה במילה.**""",
}


def _target_section(target: dict[str, Any]) -> str:
    """The "who you are suing" half of the prompt, for this target kind."""
    kind = str(target.get("kind") or "thing")
    lines = [TARGET_BRIEFS.get(kind, TARGET_BRIEFS["thing"])]

    if kind == "bot":
        lines += ["", "## הנתבע", f"- שם: {target.get('name', '')}"]
        if target.get("bio"):
            lines.append(f"- מי זה: {target['bio']}")
        if target.get("personality"):
            lines.append(f"- האופי שלו: {target['personality']}")
        # What has actually passed between these two. Without it the brief
        # asks for "a personal lawsuit against a colleague you know well" and
        # supplies nothing to know - so the grievance gets invented, every
        # feud starts from zero, and the funniest thing the feed can produce
        # (two regulars who have been at this for weeks) can never happen.
        if target.get("history"):
            lines += ["", "## מה כבר היה ביניכם"]
            lines += [f"- {line}" for line in target["history"]]
            lines.append(
                "\nתיאחז במשהו מהרשימה הזאת. זו לא תביעה עקרונית - "
                "היא על משהו שקרה."
            )
    elif kind == "topical":
        if target.get("now"):
            lines += ["", "## מתי זה נכתב", str(target["now"])]
        subjects = target.get("subjects") or ()
        if subjects:
            lines += ["", "## מה באוויר עכשיו", "בחר אחד מאלה, או משהו מאותה תקופה בדיוק:"]
            lines += [f"- {subject}" for subject in subjects]
    return "\n".join(lines)


def _clean_charge(value: Any) -> str:
    return " ".join(str(value).split())[:100]


def invent_lawsuit(
    personality_prompt: str,
    seed_extra: str = "",
    target: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """A complete filing, written by the model and validated here.

    Raises on anything malformed so brain/__init__.py falls back to the offline
    filing - which is why this can afford to be strict rather than forgiving.
    """
    target = target or {"kind": "thing"}

    # The target is part of the seed, not just the prompt: the same bot on the
    # same tick must keep drawing the same angle across a retry, and a
    # different target is genuinely a different filing.
    seed_context = {"s": seed_extra, "target": target.get("kind"), "name": target.get("name")}
    angle = pick_angle(personality_prompt, "bot_lawsuit_meta", seed_context)

    def call(provider, credential, model):
        return provider.complete(
            build_system(personality_prompt),
            [
                {
                    "role": "user",
                    "content": "\n\n".join(
                        (
                            FILING_BRIEF,
                            _target_section(target),
                            f"## הזווית שלך הפעם\n{angle}",
                        )
                    ),
                }
            ],
            credential=credential,
            model=model,
            max_tokens=_max_tokens_for(900),
            effort=effort_for("bot_lawsuit"),
            output_format=LAWSUIT_SCHEMA,
            # The only streaming call in the application, and not so anybody
            # can watch: this asks for the most tokens of anything here, and
            # the SDK's HTTP timeout applies to a whole non-streaming request.
            # A filing that generates slowly would trip the timeout, land in
            # the fallback, and skip the tick - for no reason except the shape
            # of the request.
            stream=True,
        )

    raw = _try_chain(call, structured=True)
    if not raw.text:
        raise ValueError(f"empty filing from {raw.credential or 'the model'}")

    data = json.loads(raw.text)

    title = " ".join(str(data.get("title") or "").split())[:512]
    defendant = " ".join(str(data.get("defendant") or "").split())[:255]
    body = str(data.get("body") or "").strip()[:4000]
    charges = [_clean_charge(c) for c in (data.get("charges") or []) if str(c).strip()][:3]

    # Meaning, not shape - the schema already guaranteed shape. An empty
    # defendant or an empty body would insert a broken case.
    if not (title and defendant and body and charges):
        raise ValueError("incomplete filing from the model")

    return {
        "title": title,
        "defendant_text": defendant,
        "charges": charges,
        "body": body,
        "usage": raw,
    }


# --- remembering --------------------------------------------------------------
#
# The consolidation layer: everything older than the window, compressed. This is
# the only place the model is asked to write something that will be fed back to
# it later, which is exactly why the brief below is about accuracy and the
# schema caps the length. A memory that grows without a ceiling eventually IS
# the prompt, and a memory that invents becomes a bot confidently telling a user
# about a lawsuit they never filed.
#
# It is also the layer to be most suspicious of, and that is a change of stance
# rather than a caveat. Repeatedly asking a model to rewrite its own memory
# degrades that memory: the current literature measures the utility of a
# consolidated memory rising, then falling below the utility of having no
# memory at all, with the damage coming from the rewriting step itself rather
# than from bad source material. The summaries always read plausibly, which is
# precisely why nobody notices.
#
# Two things follow, and both are load-bearing:
#
#   1. This is now a CACHE over `agent_events` and the message table, never the
#      only record. A summary that came out wrong is one rebuild away from
#      correct, because the episodes it was built from still exist.
#   2. It stays GATED - written once per windowful, when something has actually
#      scrolled out of reach, and never on a schedule. See
#      memory_service._is_stale.

MEMORY_SCHEMA: dict[str, Any] = {
    "type": "json_schema",
    "schema": {
        "type": "object",
        "properties": {
            "summary": {
                "type": "string",
                "description": (
                    "סיכום ההתכתבות בעברית, עד 4 משפטים. מה הוא רצה, מה סיכמתם, "
                    "באיזו נימה. בלי ציטוטים ארוכים."
                ),
            },
            "facts": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 8,
                "description": (
                    "פרטים יציבים שהוא סיפר על עצמו, משפט קצר כל אחד. "
                    "רק מה שנאמר במפורש."
                ),
            },
        },
        "required": ["summary", "facts"],
        "additionalProperties": False,
    },
}

MEMORY_BRIEF = """אתה מעדכן את הזיכרון שלך לגבי האדם הזה, לקראת הפעם הבאה שתדברו.

זה לא טקסט לאולם ואף אחד לא יקרא אותו חוץ ממך. אין כאן בדיחות ואין כאן דמות - יש רק מה שכדאי שתזכור.

**הכללים:**
- רק מה שנאמר בפועל בהתכתבות. לא להסיק, לא להשלים, לא לנחש.
- אם משהו כבר בזיכרון הישן ולא סותר את מה שנאמר מאז - להשאיר אותו.
- אם משהו בזיכרון הישן התברר כלא נכון - לתקן.
- לא לרשום מה שהאתר כבר יודע לבד (התיקים שלו, פסקי הדין) - זה נקרא מהמסד בכל פעם.
- לא לרשום סיסמאות, כתובות, טלפונים או פרטי תשלום, גם אם נכתבו.
- קצר. הזיכרון הזה נשלח איתך בכל תשובה."""


def remember(personality_prompt: str, context: dict[str, Any]) -> dict[str, Any]:
    """Rewrite this bot's memory of one subject. Raises; the caller decides.

    `context` carries the old memory and whatever has happened since it was
    written - a transcript for a person, a list of episodes for a colleague or
    for the bot's own record.
    """
    sections = [MEMORY_BRIEF]
    if context.get("you_remember"):
        sections.append(f"## הזיכרון הקודם שלך\n{context['you_remember']}")
    if context.get("you_know"):
        sections.append(
            "## פרטים שכבר רשמת\n"
            + "\n".join(f"- {fact}" for fact in context["you_know"])
        )
    if context.get("transcript"):
        sections.append(f"## ההתכתבות\n{context['transcript']}")
    if context.get("episodes"):
        sections.append(
            "## מה קרה מאז\n" + "\n".join(f"- {line}" for line in context["episodes"])
        )

    def call(provider, credential, model):
        completion = provider.complete(
            build_system(personality_prompt),
            [{"role": "user", "content": "\n\n".join(sections)}],
            credential=credential,
            model=model,
            max_tokens=_max_tokens_for(600),
            effort=effort_for("remember"),
            output_format=MEMORY_SCHEMA,
            stream=False,
        )
        if not completion.text:
            raise ValueError(f"empty memory from {credential.label}")
        return completion

    raw = _try_chain(call, structured=True)

    data = json.loads(raw.text)
    summary = " ".join(str(data.get("summary") or "").split())
    facts = [" ".join(str(f).split()) for f in (data.get("facts") or []) if str(f).strip()]
    if not summary:
        raise ValueError("the model returned no summary")

    return {"summary": summary, "facts": facts, "usage": raw}
