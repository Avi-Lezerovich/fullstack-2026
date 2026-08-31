"""The optional live backend - one provider-neutral seam.

Only used when the configured provider is actually credentialed. The provider
SDK is imported inside its completion function so the package stays genuinely
optional - the application, the test suite and the Docker image all still run
without it, on the offline generator.

Adding a provider is one entry in `PROVIDERS` and nothing else. Everything
above this module - the prompt, the tasks, the callers - is unchanged by that,
which is the whole reason no vendor is named outside this file.

Providers do not agree on what "credentialed" means, so each one says for
itself: Bedrock authenticates through the AWS credential chain and has no API
key at all, while the direct Anthropic API has nothing but one.

This module is allowed to raise. Every failure mode - unknown provider, missing
package, missing credentials, bad key, rate limit, timeout, empty completion,
network down - lands in the same `except` in brain/__init__.py and falls back to
the offline generator. The worker therefore has no LLM-shaped failure mode.

--- on getting interesting text out of it -------------------------------------

The first version of this file asked for "a sentence or two, in Hebrew, in
character" and got back exactly what it asked for: correct, in-character, and
identical in shape every single time. Three things fixed that, and they are all
prompt-side, because **the sampling parameters no longer exist**: temperature,
top_p and top_k were removed from the Messages API on current models and are
rejected outright, so variety cannot be bought with a dial.

1. The system prompt describes a *world* and a *register*, not a word count.
2. The task briefs are directorial - they name moves the character can make -
   instead of prescribing one shape to fill in.
3. Every call draws a seeded ANGLE: one rhetorical move plus a length. It is
   seeded from the same hash the offline generator uses, so two jurors on one
   case pull different angles while a retried tick reproduces its own.
"""

from __future__ import annotations

import json
import logging
import random
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable

from ..config import get_settings
from . import offline

log = logging.getLogger(__name__)


SYSTEM_PREAMBLE = """אתה דמות קבועה ב-LolSuit: בית משפט סאטירי בעברית שבו מתנהלים משפטים אמיתיים לגמרי על עוולות קטנות לגמרי.

תובעים כאן את יום שני. את הקפה שהתקרר. את השכן מלמעלה, את הגרביים שנעלמו בכביסה, את הרמזור שמתחלף רק כשמגיעים אליו. יש כתב תביעה, יש עדים, יש חבר מושבעים, ויש פסק דין.

**הבדיחה כולה היא הפער**: הצורה רצינית לחלוטין, הנושא מגוחך לחלוטין. אף אחד כאן לא קורץ למצלמה ואף אחד לא מסביר שזה מצחיק. ככל שתתייחס לגרב האבודה ברצינות תהומית יותר - כך זה עובד טוב יותר."""


# The rules that actually stop the output reading like a form letter. Phrased
# as prohibitions where a prohibition is unambiguous, and as invitations where
# the point is to open a door.
STYLE_RULES = """## איך כותבים כאן

הכללים בלשון מקור בכוונה - הם נכונים לכל דמות, בכל מגדר.

- **להיות ספציפי לתיק הזה.** לתפוס פרט אחד קטן ומוזר מהתביעה ולהיאחז בו. לא לסכם את התיק - כולם קראו אותו.
- **לא לפתוח פעמיים באותה צורה.** אם משפט הפתיחה יכול היה להתאים לכל תיק אחר באתר - למחוק אותו ולהתחיל אחרת.
- **להפתיע.** דימוי קונקרטי, מספר מדויק להחריד, תקדים משפטי שהומצא ברגע זה ומצוטט בביטחון מלא, פרט אישי זעיר מהחיים שמחוץ לאולם.
- **קול, לא ניסוח.** לא "לכתוב בסגנון" - להיות הדמות. אם יש לה מילת מפתח משלה, קללה מנומסת, או תחביב שהיא גוררת לכל דיון - להשתמש בו.
- אורך: קצר. אבל לא תמיד באותו אורך.

## אסור

- כותרות, נקודות, כוכביות, מספור, אימוג'ים.
- מרכאות סביב התשובה, או הקדמה מסוג "הנה מה שאני אומר".
- להסביר את הבדיחה, לקרוץ, או לציין שהמצב אבסורדי. המצב אבסורדי. יש להתייחס אליו בכובד ראש.
- קלישאות משפטיות גנריות שלא אומרות כלום על התיק הזה דווקא.

יש להחזיר אך ורק את הטקסט עצמו, כאילו נאמר באולם."""


# What each task is, described as a situation the character is standing in
# rather than as an output format.
TASK_BRIEFS: dict[str, str] = {
    "jury_deliberation": (
        "אתה מושבע. אתה מדבר עכשיו בקול, באולם, מול שאר המושבעים ומול הצדדים. "
        "תגיד את הדבר האחד שאתה חושב על התיק - נימוק, תהייה, התפרצות, או הערה "
        "צדדית שמסגירה בדיוק איזה מין אדם אתה. אתה לא מכריע, אתה מדבר."
    ),
    "verdict": (
        "אתה השופט, וזה רגע ההכרעה. ההצבעה כבר נספרה ואתה יודע את התוצאה - "
        "עכשיו תנסח אותה. אפשר בנזיפה, אפשר באנחה, אפשר במשפט אחד יבש שנוחת "
        "כמו פטיש. תגיד את ההכרעה במפורש, ותעשה את זה בדרך שלך."
    ),
    "sentence": (
        "אתה השופט וגזרת דין חובה. תמציא עונש. הוא חייב להיות **ספציפי, "
        "מדיד ומגוחך** - לא 'קנס' אלא בדיוק כמה ובדיוק במה; לא 'התנצלות' אלא "
        "באיזה פורמט, באיזה אורך ובפני מי. עונש טוב הוא כזה שאפשר לדמיין "
        "מישהו מבצע בפועל, ולסבול איתו."
    ),
    "moderation_note": (
        "אתה בוט פיקוח וסיימת לבדוק תוכן. תרשום הערה קצרה: מה נבדק ומה הוחלט. "
        "זו ההזדמנות היחידה שלך לדבר, אז תשמע כמו עצמך ולא כמו מדפסת."
    ),
    "draft_lawsuit": (
        "אתה עוזר הניסוח של בית המשפט, ומישהו ביקש שתנסח לו כתב תביעה. "
        "תכתוב את גוף התביעה: מה קרה, למה זה בלתי נסבל, ומה מבקשים מבית המשפט. "
        "רצינות משפטית מלאה בשירות תלונה קטנטנה. שתיים-שלוש פסקאות קצרות."
    ),
    "bot_lawsuit": (
        "אתה מגיש כתב תביעה משלך, ביוזמתך, כי נמאס לך. תכתוב את גוף התביעה: "
        "מה הנתבע עשה, מתי זה חצה את הגבול, ומה אתה דורש. שתיים-שלוש פסקאות "
        "קצרות, ובאופי שלך."
    ),
    "suggest_comment": (
        "מישהו קורא תיק ורוצה להגיב עליו, ואתה מציע לו ניסוח. תגובה אחת, חדה, "
        "כזו שמישהו באמת היה כותב מתחת לפוסט - לא הודעה רשמית."
    ),
    "bot_comment": (
        "אתה גולש באתר ותיק אחד תפס לך את העין. תגיב עליו כמו שמגיבים ברשת: "
        "קצר, מיידי, בלי פתיחה מנומסת. אתה לא באולם עכשיו - אתה בטלפון."
    ),
    "bot_reply": (
        "מישהו שלח לך הודעה פרטית ואתה עונה לו. זו שיחה בין שניים, לא הצהרה "
        "לפרוטוקול - תהיה ישיר, תתייחס למה שהוא כתב בפועל, ותישאר בדיוק אותה "
        "דמות שאתה באולם."
    ),
}


# --- the angle: what keeps two calls from sounding like one -------------------
#
# One move plus one length, drawn per call from the deterministic seed. This is
# the whole variety mechanism now that temperature is gone from the API.

MOVES: tuple[str, ...] = (
    "פתח בפרט קטן ומוזר מהתיק והיצמד אליו עד הסוף.",
    "המצא תקדים משפטי שלא קיים, וצטט אותו בביטחון גמור.",
    "ספר בחצי משפט על משהו שקרה לך פעם, ואז חזור לתיק.",
    "פנה ישירות אל הנתבע, בגוף שני.",
    "התחל מהמסקנה, ורק אחר כך הסבר איך הגעת אליה.",
    "שאל שאלה אחת שאיש לא טרח לשאול כאן.",
    "השווה את המקרה למשהו מתחום אחר לגמרי - ספורט, בישול, גיאולוגיה.",
    "נקוב במספר מדויק להחריד, ואל תסביר מאיפה הוא.",
    "הסכם עם הצד השני, ואז הפוך את ההסכמה נגדו.",
    "התחל בהתנצלות קטנה על מה שאתה עומד לומר, ואז אמור את זה בכל זאת.",
    "התייחס למשהו שקרה בתיק אחר לגמרי, כאילו כולם זוכרים אותו.",
    "תאר את הרגע עצמו כאילו היית שם וראית.",
    "התחל במילה אחת, נקודה, ואז המשך.",
    "תקן מונח שמישהו השתמש בו לא נכון, וממשיך משם.",
    "הודה שאתה מתלבט, ואז הכרע בכל זאת.",
    "צטט את כתב התביעה מילה במילה, ואז תגיד מה חשבת כשקראת.",
    "התחל באנחה מנוסחת, לא בסימן קריאה.",
    "הצע פתרון מעשי לגמרי ובלתי אפשרי לגמרי.",
    "אמור את ההפך ממה שמצפים ממך, ותנמק ברצינות.",
)

LENGTHS: tuple[str, ...] = (
    "משפט אחד, קצר.",
    "משפט אחד ארוך ומתפתל.",
    "שני משפטים.",
    "שני משפטים: אחד ארוך, אחד קצר שנוחת.",
    "שלושה משפטים קצרים.",
)

# Long-form tasks write paragraphs; a "one short sentence" dial would fight the
# brief instead of colouring it.
_LONG_FORM = {"draft_lawsuit", "bot_lawsuit"}


def pick_angle(personality_prompt: str, task: str, context: dict[str, Any]) -> str:
    """One rhetorical move (and a length, where length is a real choice).

    Seeded from `offline.seed_for`, so this is reproducible exactly like the
    offline generator: the same juror on the same case always draws the same
    angle, and two jurors on one case draw different ones.
    """
    rng = random.Random(offline.seed_for(personality_prompt, task, context))
    move = rng.choice(MOVES)
    if task in _LONG_FORM:
        return move
    return f"{move}\n{rng.choice(LENGTHS)}"


# --- prompt assembly ----------------------------------------------------------

# Only the fields worth spending context on, in the order a person would read
# them. `case_id` and the vote counts are deliberately absent from most of it:
# a juror quoting the tally back at the room is the kind of thing that made the
# old output read like a database dump.
_CONTEXT_LABELS: tuple[tuple[str, str], ...] = (
    ("case_title", "כותרת התביעה"),
    ("defendant", "הנתבע"),
    ("plaintiff", "התובע"),
    ("charges", "סעיפי האישום"),
    ("case_body", "כתב התביעה"),
    ("testimonies", "עדויות שנשמעו"),
    ("tally_guilty", "קולות 'חייב'"),
    ("tally_not_guilty", "קולות 'זכאי'"),
    ("verdict", "ההכרעה שהתקבלה"),
)

_VERDICT_WORDS = {"guilty": "חייב", "not_guilty": "זכאי"}

# Which tasks are allowed to see the outcome fields.
#
# A juror deliberating has not voted yet, so telling them the verdict and the
# tally invites the model to announce a result the trial has not reached - the
# jury would be reading out the ending mid-scene. In practice
# `trial_service._case_context` withholds those fields until the verdict step,
# so this is belt-and-braces; but it is the kind of thing that breaks silently
# the first time a caller passes a fuller context, and the symptom (a juror who
# "knows") would be baffling to debug.
_OUTCOME_FIELDS = frozenset({"tally_guilty", "tally_not_guilty", "verdict"})
_KNOWS_OUTCOME = frozenset({"verdict", "sentence"})


def build_prompt(task: str, context: dict[str, Any], angle: str = "") -> str:
    """The user turn: what the situation is, then what to do with it."""
    brief = TASK_BRIEFS.get(task, "כתוב טקסט קצר ומתאים באופי שלך, בעברית.")
    lines = [brief]

    knows_outcome = task in _KNOWS_OUTCOME

    details: list[str] = []
    for key, label in _CONTEXT_LABELS:
        if key in _OUTCOME_FIELDS and not knows_outcome:
            continue
        value = context.get(key)
        if value in (None, "", [], {}):
            continue
        if isinstance(value, (list, tuple)):
            value = "; ".join(str(item) for item in value)
        elif key == "verdict":
            # "guilty" in the middle of a Hebrew prompt is a seam showing.
            value = _VERDICT_WORDS.get(str(value), value)
        details.append(f"- {label}: {value}")

    if details:
        lines += ["", "## התיק", *details]
    if angle:
        lines += ["", "## הזווית שלך הפעם", angle]
    return "\n".join(lines)


def build_system(personality_prompt: str) -> str:
    """World, then character, then house style.

    The character sits in the middle on purpose: it is the part the model
    should weigh most heavily, and it reads as the answer to the world the
    preamble just described.
    """
    return "\n\n".join(
        (SYSTEM_PREAMBLE, f"## מי אתה\n\n{personality_prompt.strip()}", STYLE_RULES)
    )


def _text_of(message: Any) -> str:
    """The text blocks of a Messages response, concatenated."""
    return "".join(
        block.text for block in message.content if getattr(block, "type", "") == "text"
    ).strip()


# Adaptive thinking with a low effort budget, rather than thinking disabled.
# Disabling it on current models is the documented cause of two failure modes
# (a tool call written into visible text, and leaked internal tags), and the
# original reason for disabling it here - that thinking tokens would eat a tiny
# max_tokens - is handled properly below by not setting a tiny max_tokens.
# These are one-line quips: "low" is the right end of the effort range.
_THINKING = {"type": "adaptive"}
_EFFORT = "low"


def _max_tokens_for(max_chars: int) -> int:
    """Token headroom for `max_chars` of Hebrew.

    The old formula was `max_chars // 2`, which assumed the ~4 chars/token of
    English. Hebrew tokenises far worse - closer to one token per character -
    so that formula was capping the model at roughly an eighth of the text it
    was being asked for, and the completions came back truncated mid-sentence.
    Doubling it and adding a floor costs nothing (output is billed on what is
    actually generated, and `trim()` still enforces the real limit).
    """
    return max(512, max_chars * 2)


def _complete_bedrock(
    system: str,
    prompt: str,
    *,
    model: str,
    max_tokens: int,
    output_format: dict[str, Any] | None = None,
) -> str:
    """Claude on Amazon Bedrock, via the SDK's Mantle (Messages API) client.

    Credentials come from the standard AWS chain - AWS_ACCESS_KEY_ID and
    friends, a shared profile named by AWS_PROFILE, or the EC2/ECS role - and
    never from LLM_API_KEY. Region is the one thing the client will not infer,
    which is why AWS_REGION is what gates this provider.
    """
    from anthropic import AnthropicBedrockMantle

    settings = get_settings()
    client = AnthropicBedrockMantle(
        aws_region=settings.aws_region,
        timeout=settings.llm_timeout_seconds,
        max_retries=1,
    )

    message = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        thinking=_THINKING,
        output_config=_output_config(output_format),
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    return _text_of(message)


def _complete_anthropic(
    system: str,
    prompt: str,
    *,
    model: str,
    max_tokens: int,
    output_format: dict[str, Any] | None = None,
) -> str:
    """Claude on the direct Anthropic API, keyed by LLM_API_KEY."""
    import anthropic

    settings = get_settings()
    client = anthropic.Anthropic(
        api_key=settings.llm_api_key,
        timeout=settings.llm_timeout_seconds,
        max_retries=1,
    )

    message = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        thinking=_THINKING,
        output_config=_output_config(output_format),
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    return _text_of(message)


# The keys a gateway might name its completion, best first. The endpoint this
# was built against returns `text`; the others cost nothing to accept and save
# the next person a debugging session if theirs differs.
_GATEWAY_TEXT_KEYS = ("text", "completion", "response", "output")


def _strip_fence(text: str) -> str:
    """Drop a ```json ... ``` wrapper if the model added one.

    Asking for JSON in a prompt gets JSON, but a model that has been told to
    return JSON its whole life will sometimes dress it in a markdown fence.
    The Bedrock and direct providers never need this - they get a real schema
    enforced by the API - so it lives here, with the provider that has to ask
    nicely instead.
    """
    if not text.startswith("```"):
        return text
    body = text.split("\n", 1)[-1] if "\n" in text else ""
    return body.rsplit("```", 1)[0].strip()


def _complete_gateway(
    system: str,
    prompt: str,
    *,
    model: str,
    max_tokens: int,
    output_format: dict[str, Any] | None = None,
) -> str:
    """Claude behind an HTTP endpoint that holds the real credentials for us.

    This is the provider for a deployment that has no AWS identity of its own.
    An API Gateway key opens exactly one POST route, and whatever sits behind
    it - a Lambda, in the case this was written for - is what actually talks to
    Bedrock. Nothing here needs an SDK, an AWS region, or a credential chain,
    which is the entire appeal: it works from any box, including one with no
    instance role.

    `model` and `max_tokens` are accepted to satisfy the provider signature and
    then ignored, because the far side chooses both. That is a real limitation,
    not an oversight - see the two below, which are the same shape.

    Two things the endpoint does not implement, worked around here:

    * **No system turn.** It reads one `prompt` field and silently drops the
      rest. Passing the system prompt as its own key returns a cheerful 200
      with the character quietly missing - the model answers as a generic
      assistant - so the two are folded into one string instead.
    * **No structured output.** There is nowhere to put `output_config.format`,
      so a schema is demoted to an instruction in the prompt and the fence is
      stripped off the answer. `invent_lawsuit` still validates what comes
      back, and still raises into the offline fallback when it is wrong.
    * **A hard output cap, and no way to raise it.** The far side stops at its
      own limit and ignores `max_tokens`, which in Hebrew - roughly a token per
      character - lands around 450 characters, a third of what the same cap
      buys in English. Short tasks never notice. A filing written at full
      length comes back cut mid-string and fails `json.loads`, so the schema
      instruction below also asks for a length that fits.
    """
    settings = get_settings()
    if not settings.llm_endpoint:
        raise ValueError("LLM_ENDPOINT is required by the gateway provider")

    text_prompt = f"{system}\n\n{prompt}"
    if output_format is not None:
        schema = json.dumps(output_format.get("schema", {}), ensure_ascii=False)
        text_prompt += (
            "\n\n## הפורמט\n"
            "החזר אך ורק אובייקט JSON תקין, בלי טקסט לפני או אחרי ובלי גדר markdown, "
            f"לפי הסכימה הזאת:\n{schema}\n\n"
            "חשוב: כל התשובה יחד חייבת להיות קצרה מ-350 תווים. גוף "
            "התביעה: שני משפטים קצרים לכל היותר. תשובה ארוכה מזה "
            "תיקטע באמצע ותיפסל."
        )

    request = urllib.request.Request(
        settings.llm_endpoint,
        data=json.dumps({"prompt": text_prompt}).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json", "x-api-key": settings.llm_api_key},
    )
    with urllib.request.urlopen(request, timeout=settings.llm_timeout_seconds) as response:
        payload = json.loads(response.read().decode("utf-8"))

    text = ""
    if isinstance(payload, dict):
        for key in _GATEWAY_TEXT_KEYS:
            value = payload.get(key)
            if isinstance(value, str):
                text = value
                break

    text = text.strip()
    return _strip_fence(text) if output_format is not None else text


def _output_config(output_format: dict[str, Any] | None) -> dict[str, Any]:
    """`effort` always, `format` only when a task needs parseable output."""
    config: dict[str, Any] = {"effort": _EFFORT}
    if output_format is not None:
        config["format"] = output_format
    return config


@dataclass(frozen=True)
class Provider:
    """One backend: how to call it, when it is usable, what it runs by default."""

    complete: Callable[..., str]
    # Given a Settings, is this provider credentialed enough to be worth trying?
    # Cheap and local - a real check would mean a network round trip on every
    # health poll. Anything it cannot see (a missing SDK, an expired role, a
    # revoked key) surfaces as a failed call, falls back like any other error,
    # and is reported by /api/health via brain.LAST_CALL.
    is_configured: Callable[[Any], bool]
    # Bedrock namespaces its model ids; the direct API does not.
    default_model: str


PROVIDERS: dict[str, Provider] = {
    "bedrock": Provider(
        complete=_complete_bedrock,
        is_configured=lambda settings: bool(settings.aws_region),
        default_model="anthropic.claude-opus-5",
    ),
    "anthropic": Provider(
        complete=_complete_anthropic,
        is_configured=lambda settings: bool(settings.llm_api_key),
        default_model="claude-opus-5",
    ),
    "gateway": Provider(
        complete=_complete_gateway,
        # Both halves matter: the key alone cannot say where to send itself.
        is_configured=lambda settings: bool(
            settings.llm_api_key and settings.llm_endpoint
        ),
        # The endpoint picks the model, so there is no default to name here.
        default_model="",
    ),
}


def is_configured(settings: Any) -> bool:
    """Whether the configured provider is set up enough to try at all."""
    provider = PROVIDERS.get(settings.llm_provider)
    return provider is not None and provider.is_configured(settings)


def _provider_and_model(settings: Any) -> tuple[Provider, str]:
    name = settings.llm_provider
    provider = PROVIDERS.get(name)
    if provider is None:
        raise ValueError(
            f"unknown LLM_PROVIDER {name!r}; known: {', '.join(sorted(PROVIDERS))}"
        )
    return provider, (settings.llm_model or provider.default_model)


def generate(
    personality_prompt: str,
    task: str,
    context: dict[str, Any],
    *,
    max_chars: int = 400,
) -> str:
    """Ask the configured provider. Raises on any failure; the caller falls back."""
    settings = get_settings()
    provider, model = _provider_and_model(settings)

    text = provider.complete(
        build_system(personality_prompt),
        build_prompt(task, context, pick_angle(personality_prompt, task, context)),
        model=model,
        max_tokens=_max_tokens_for(max_chars),
    )

    if not text:
        # An empty completion is a failure, not a valid answer - falling back
        # gives the user something in character instead of a blank comment.
        raise ValueError(f"empty completion from {settings.llm_provider}")

    return text


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
    settings = get_settings()
    provider, model = _provider_and_model(settings)
    target = target or {"kind": "thing"}

    # The target is part of the seed, not just the prompt: the same bot on the
    # same tick must keep drawing the same angle across a retry, and a
    # different target is genuinely a different filing.
    seed_context = {"s": seed_extra, "target": target.get("kind"), "name": target.get("name")}
    angle = pick_angle(personality_prompt, "bot_lawsuit_meta", seed_context)

    raw = provider.complete(
        build_system(personality_prompt),
        "\n\n".join(
            (
                FILING_BRIEF,
                _target_section(target),
                f"## הזווית שלך הפעם\n{angle}",
            )
        ),
        model=model,
        max_tokens=_max_tokens_for(900),
        output_format=LAWSUIT_SCHEMA,
    )
    if not raw:
        raise ValueError(f"empty filing from {settings.llm_provider}")

    data = json.loads(raw)

    title = " ".join(str(data.get("title") or "").split())[:512]
    defendant = " ".join(str(data.get("defendant") or "").split())[:255]
    body = str(data.get("body") or "").strip()[:4000]
    charges = [_clean_charge(c) for c in (data.get("charges") or []) if str(c).strip()][:3]

    # Meaning, not shape - the schema already guaranteed shape. An empty
    # defendant or an empty body would insert a broken case.
    if not (title and defendant and body and charges):
        raise ValueError("incomplete filing from the model")

    return {"title": title, "defendant_text": defendant, "charges": charges, "body": body}
