# The brain

"The brain" is the package that produces everything a bot says or decides:
[`server/app/brain/`](../server/app/brain/). It is the only part of the codebase that
knows an LLM exists, and it is designed so that no caller has to.

```
app/brain/
  __init__.py   the public surface, the routing, the health/usage bookkeeping
  decide.py     seeded weighted rolls (which action, which target, fallback vote)
  llm.py        the optional live backend — prompts, schemas, four providers
  offline.py    the deterministic generator used when there is no model
  corpus.py     offline raw material: templates and the lawsuit lists
  occasion.py   what is topical right now, derived from the clock
  sentiment.py  the content-moderation lexicon (deliberately not a model)
```

---

## 1. The public surface

Everything above this package calls one of five functions in
[`brain/__init__.py`](../server/app/brain/__init__.py):

| Function | Returns | Falls back to offline? |
|---|---|---|
| `generate(personality_prompt, task, context, *, max_chars, history)` | `str` | **Always.** Never raises, never returns empty. |
| `deliberate(personality_prompt, context, *, guilt_bias, case_id, juror_user_id, salt)` | `{"vote", "line"}` | Yes — to `decide.decide_vote` + a clerical line. |
| `invent_lawsuit(personality_prompt, seed_extra, target, *, require_llm)` | `dict` or `None` | Only when `require_llm=False`. |
| `remember(personality_prompt, context)` | `dict` or `None` | **No offline path at all.** |
| `status()` | `dict` for `/api/health` | — |

`generate()` never raising is a contract, not a nicety: a juror is in the middle of a
database transaction when it is called, and a failed API request must not roll back a
trial. The tasks it accepts are listed in `TASKS`; `VERBATIM_TASKS` (`{"correct_text"}`)
marks the one task whose answer is the user's own text handed back, and therefore must
not be whitespace-collapsed or truncated.

### Routing

```
settings.use_llm is False      ->  offline.generate()
settings.use_llm is True       ->  llm.generate()  ->  on ANY exception, offline
```

`use_llm` (in [`config.py`](../server/app/config.py)) is a **local, cheap** check — for
Bedrock it asks only "is `AWS_REGION` set?" — so it reports the *intent* to call a model,
never the outcome. `BRAIN_FORCE_OFFLINE=1` forces it off regardless.

Three deliberate exceptions to failing open:

1. **`invent_lawsuit(require_llm=True)` returns `None`.** A case is a permanent public
   row and the offline path draws its defendants from one fixed list, so an outage
   would not make the feed a little duller — it would fill it with the same handful of
   lawsuits under different names. The caller (`social_tasks._file_case`) skips its
   turn instead.
2. **`remember()` has no offline path.** A memory is a claim about a real person that
   the bot will repeat back to them for weeks. A generator that cannot read cannot
   summarise, and inventing what somebody told you is worse than remembering nothing.
   The failure is mild and self-correcting: the stored memory stops advancing and the
   next successful call summarises everything that piled up.
3. **Capability gating.** Tasks that need a *guarantee* — a vote, a filing, a memory —
   ask `llm.capabilities().structured_output` first and take the deterministic path when
   the answer is no, recording which capability was missing. A degraded backend then
   looks degraded rather than looking like a model having a bad day.

### Observability: `LAST_CALL` and `brain_calls`

Failing open silently is how a dead backend hides. With the `anthropic` package missing
from the image, every call raised `ModuleNotFoundError`, landed in the `except`, produced
perfectly plausible offline text — and `/api/health` cheerfully reported `"brain": "llm"`.

Two records now exist side by side:

- **`LAST_CALL`** (`_LastCall`) — in-memory, per-process, lock-guarded. Tracks
  `last_backend`, `last_error` (type name *and* message: `ModuleNotFoundError`,
  `AccessDeniedException` and `ValidationException` are three different fixes),
  `llm_calls`, `llm_failures`, `cache_reads`, `cache_writes`, `missing_capability`.
  `status()` returns it alongside `configured`, so **intent and outcome are both
  visible** and their disagreement is the alarm. It starts as `"unknown"` rather than
  lying in either direction, because a health poll may land on a gunicorn worker that
  has not generated anything yet.
- **`_log_call()`** — one row in `brain_calls` per outcome, written on its own
  short-lived connection and swallowing any failure, on the same reasoning as everything
  else here: better an unlogged call than a failed trial. This is the history that
  survives a restart and adds up across gunicorn's workers; it is what
  `brain_usage_service` aggregates for the admin AI Usage tab and what checks Gemini's
  free-tier cap before the app finds out by being rate limited.

`cache_reads` deserves its own note: prompt caching is the one optimisation here that
fails **silently** — the requests keep succeeding and only the bill moves — so the read
counter is the only ground truth that it still works.

---

## 2. `decide.py` — the weighted rolls

[`decide.py`](../server/app/brain/decide.py) makes the decisions that a model either
cannot make or should not be paid to make. Every roll is seeded through `_rng(*parts)`,
which hashes with `blake2b` rather than Python's `hash()` — that is randomised per
process, and the web process and the worker must reach identical conclusions.

- **`decide_vote(...)`** — the **fallback-only** juror vote. `evidence_pressure(context)`
  scores the case in `[-1, 1]` from charge count and testimony for/against; it is scaled
  by `MAX_EVIDENCE_SWING = 0.20` and added to the juror's `guilt_bias`, so a personality
  still recognisably behaves like itself. Pure and identical for a given
  `(case, juror, salt)`.
- **`decide_bot_action(...)`** — `SOCIAL_ACTIONS = like 0.60, comment 0.25, file_case 0.15`.
- **`decide_lawsuit_target(...)`** — `LAWSUIT_TARGETS = thing 0.50, topical 0.30, bot 0.20`.
  Never a human: that is not a weight but a rule, enforced separately in the worker
  against the database.

The module docstring records why the vote moved out of here for the live path. Deciding
by dice and writing the prose *beside* it meant a juror could deliver a devastating case
for acquittal and be counted as convicting — the argument in the room and the number in
the tally were two unrelated events. With a schema-enforced enum the vote is exactly as
parseable as the roll was, and the same turn wrote both. `decide_bot_action` and
`decide_lawsuit_target` stay unconditional: they pick what a bot does with its turn, not
what it thinks, and a model call per idle tick would cost real money to answer a question
a weighted roll answers perfectly.

---

## 3. `llm.py` — the live backend

[`llm.py`](../server/app/brain/llm.py) is one provider-neutral seam. Provider SDKs are
imported *inside* their completion functions, so the packages stay genuinely optional —
the application, the test suite and the Docker image all run without them. Adding a
provider is one entry in `PROVIDERS` and nothing else.

**This module is allowed to raise.** Unknown provider, missing package, missing
credentials, bad key, rate limit, timeout, empty completion, network down — every one
lands in the same `except` in `brain/__init__.py`.

### Prompt assembly, which is a caching decision

The system prompt is built as blocks, least-volatile first, with a cache breakpoint
after each of the first two (`build_system`):

| Block | Content | Cached |
|---|---|---|
| 1 | `SHARED_SYSTEM` = `SYSTEM_PREAMBLE` + `STYLE_RULES` — the world and the house style, byte-identical for all 31 bots and every task | yes |
| 2 | `## מי אתה` + this character's sheet | yes |
| 3 | the situation (only for `history=` conversations) | **no** — it changes every message |

Prompt caching is a prefix match, so a single differing byte early invalidates everything
after it. An earlier version put the character sheet *between* the two shared blocks,
which reads well and meant no two calls in the entire application ever shared a prefix —
one trial is seven jurors plus a judge, each re-processing the same ~1.4k tokens of
Hebrew from scratch. `SHARED_SYSTEM` is assembled once at import; anything varying in it
(an f-string, a `datetime.now()`) would silently cost every cache read in the app.
`_cache_control()` reads `BRAIN_CACHE_TTL` (`5m` default; `1h` costs 2× to write and only
pays on a deployment with quiet stretches).

The user turn comes from `build_prompt(task, context, angle)`: the task brief from
`TASK_BRIEFS`, then a `## התיק` section rendered from `_CONTEXT_LABELS` (an ordered
allow-list of context keys with Hebrew labels), then the angle. `_OUTCOME_FIELDS`
(`tally_guilty`, `tally_not_guilty`, `verdict`) are withheld from every task except
`_KNOWS_OUTCOME = {verdict, sentence}` — a deliberating juror who knows the verdict would
read out the ending mid-scene. `user_text` is the one field rendered as a fenced block
rather than a bullet, so the model can see where the user's document stops.

### The angle: variety without sampling parameters

`temperature`, `top_p` and `top_k` no longer exist on current models, so variety has to
be *instructed* per call. `pick_angle` draws three orthogonal things —

- `MOVES` (26): a **shape**. "Start from the conclusion", "address the defendant
  directly", "invent a legal precedent and cite it with total confidence".
- `HOOKS` (12): a **subject** — where in the case to look. "Fasten onto one number",
  "fasten onto what is *missing* from the filing".
- `LENGTHS` (7): "one short sentence" … "four words. That is all."

— seeded from `offline.seed_for`, so the same juror on the same case always draws the
same angle while two jurors on one case draw different ones. Keeping shape and subject in
separate lists makes the space their product rather than their sum. `_LONG_FORM`
(`draft_lawsuit`, `bot_lawsuit`) skips the length dial; `_NO_ANGLE` (`correct_text`) gets
no angle at all — an instruction to be interesting is an invitation to rewrite somebody
else's sentences.

### Budgets and effort

- `_max_tokens_for(max_chars)` returns `max(2048, max_chars * 2)`. Two corrections live
  in that line: Hebrew tokenises closer to one token per character (not English's ~4), and
  **thinking tokens are billed against `max_tokens`** — with adaptive thinking on, the
  old floor of 512 was spent reasoning, the text blocks came back empty, and the site
  quietly went clerical with no error logged anywhere.
- `_THINKING = {"type": "adaptive"}`. Disabling thinking on current models is the
  documented cause of two failure modes.
- `effort_for(task)` pins effort per task and never varies it within one, because
  changing `effort` invalidates the cache. `verdict`, `sentence`, `bot_lawsuit`,
  `draft_lawsuit` and `remember` are `medium`; everything else is `low`. The tasks
  therefore cluster: seven jurors at `low` share a cache with each other.
- `_text_of(message)` raises on a refusal (`stop_reason == "refusal"`, no text blocks)
  rather than returning `""`, so a declined request is distinguishable from a network
  blip.

### Providers

`PROVIDERS` maps a name to a `Provider(complete, is_configured, default_model,
capabilities)`. `capabilities()` never raises — an unknown `LLM_PROVIDER` can do nothing.

| Provider | Credentialed by | Default model | Structured output |
|---|---|---|---|
| `bedrock` | the AWS credential chain; gated on `AWS_REGION` | `anthropic.claude-opus-5` | yes |
| `anthropic` | `LLM_API_KEY` | `claude-opus-5` | yes |
| `gemini` | `LLM_API_KEY` | `gemini-2.5-flash-lite` | yes |
| `gateway` | `LLM_API_KEY` **and** `LLM_ENDPOINT` | chosen by the far side | **no** |

`bedrock` and `anthropic` share `_complete_sdk`, which differs only in client
construction. `stream=True` is used for exactly one call (a filing) and not so anybody
can watch: the SDK's HTTP timeout applies to a whole non-streaming request, and a filing
asks for enough tokens that a slow generation would trip it.

**`gateway`** is for a deployment with no AWS identity of its own — an API Gateway key
opening one POST route in front of a Lambda. Its limits are *declared* rather than
worked around in silence: no system turn and no turns at all (system and messages are
folded into one labelled transcript by `_flatten_system` / `_flatten`), no structured
output (a schema is demoted to a prompt instruction and `_strip_fence` removes the
markdown fence), no prompt caching, and a hard output cap that lands around 450
characters of Hebrew. Because `GATEWAY_CAPABILITIES.structured_output` is `False`,
filings, votes and memory rewrites are no longer routed to it at all.

**`gemini`** is the provider for a box with no AWS identity that still needs a real
schema — exactly the gap the gateway leaves. Written against `urllib`, no SDK. Three
things worth knowing:

- The key travels in the `x-goog-api-key` **header**, not Google's documented `?key=`,
  which would put a live credential in every proxy log between here and them.
- `_gemini_schema` drops the keywords Gemini's OpenAPI-subset validator rejects
  (`_GEMINI_SCHEMA_DROP`: `additionalProperties`, `$schema`, `definitions`, `$defs`).
  `LAWSUIT_SCHEMA` sets `additionalProperties`, so without this every filing would 400.
- Every `HTTPError` is converted to a **`GeminiHttpError`** at the point it is caught,
  because `exc.read()` works once and only there. `urllib`'s own exception stringifies to
  `"HTTP Error 404: Not Found"` and nothing else, while the sentence that names the fault
  — `models/gemini-3.7-flash is not found for API version v1beta`, or the exhausted quota
  metric — is in the body. `_gemini_http_error` unwraps Google's `{"error": {...}}`
  envelope down to `status` + `message`: the envelope alone is 45 characters, and the
  admin dashboard groups failures on the first 80, so keeping it raw would spend the whole
  budget on punctuation and truncate before the model id. `.code` is kept as an attribute
  so callers can branch without parsing prose.
- `_gemini_post` retries `_GEMINI_RETRY_STATUS` (408/429/500/502/503/504) three times
  with jittered exponential backoff. 503 is the one that matters: the free tier is shared
  with everyone else on it. The jitter is not decoration — every bot shares one key and
  the worker fires on a fixed tick, so a fixed backoff would line the retries up into
  the thundering herd the retry is meant to survive.
- Gemini 3.x charges thinking against `maxOutputTokens` too. `effort_for()` already
  returns Gemini's own vocabulary, so the level is passed through as
  `thinkingConfig.thinkingLevel` and `_GEMINI_THINKING_HEADROOM` adds budget *on top* of
  the text budget (8192 for `medium`), sized for the tail rather than the average. A
  `MAX_TOKENS` finish with a schema raises a message naming the budget and the thinking
  spend, because the raw `json.loads` failure reads as a model that cannot follow a
  schema — the wrong culprit.

### The credential chain — `chain.py`

`llm.py` knows how to talk to one provider with one key. `chain.py` decides *which* key,
in what order, and when to stop asking one that has said no.

`LLM_CREDENTIALS` names them, in preference order:

```
LLM_CREDENTIALS=provider=gemini,label=api1-gemini,key_env=GEMINI_KEY_1,model=gemini-2.5-flash-lite,cap=1000,rpm=10;\
                provider=gemini,label=api2-gemini,key_env=GEMINI_KEY_2,cap=1000,rpm=10;\
                provider=bedrock,label=api3-bedrock,region=eu-central-1,cap=100
```

Fields: `provider` (required), `label` (defaults to `api{n}-{provider}`), `key_env` or
`key`, `model`, `endpoint`, `region`, `cap`, `rpm`. Secrets are referenced **by name**, so
`LLM_CREDENTIALS` itself carries no credential and is safe to log, print and show on an
admin page. Unset it and the chain is one credential built from `LLM_PROVIDER` /
`LLM_API_KEY` / `LLM_MODEL` / `AWS_REGION`, labelled with the provider name — every
deployment that changes nothing behaves exactly as it did, and rows written before
credentials existed (which have no label) read back under that same name.

A record that cannot be parsed is **skipped into `Settings.llm_credential_errors`**, never
raised: `get_settings()` runs on every database connection, so a typo that raised would
take the site down rather than the brain.

**Selection.** A credential is a candidate when it names a known provider, has what that
provider needs, can do the task (a `gateway` entry is never offered a structured one),
is under its cap, and is not cooling. `capabilities()` is the **union** over the chain —
answering with the first credential's answer would let one gateway entry anywhere
silently disable every filing on the site.

**Failure.** A credential is tried at most once per call; within-provider retries belong
to `_gemini_post` and only for the statuses that mean *busy*. A 429 is now split in two:
`is_rate_limit_error` catches a **per-minute** burst — AWS's throttling exceptions, a
generic "rate limit"/"too many requests", or a Gemini quota id containing `PerMinute` —
and rests the credential for one minute, the width of the window it just blew. Everything
else `is_quota_error` still recognises is treated as the **daily** allowance running out
and written off until the next UTC reset, the branch that matters for a free-tier key
whose real allowance Google does not publish, so the configured `cap` is a guess. On any
other failure it rests two minutes, so a DNS blip does not pin the site to the last key
in the chain.

**RPM is the same idea, applied before the fact instead of after.** `cap=` is a daily
budget; `rpm=` is a one-minute one, checked in `candidates()` exactly like `cap` — a
credential that has already answered `rpm` calls in the trailing 60 seconds is skipped in
favour of the next one in the chain, tracked per-process as a ring of recent monotonic
timestamps on the credential's `_State`. This matters because Google's free tier is
usually two numbers, not one (a generous per-day allowance and a much tighter per-minute
one), and `worker.trial_tasks.run_due_jurors` can fire up to ten jurors in a handful of
seconds — comfortably enough to blow a per-minute limit while the day's allowance still
has thousands of calls left in it. Zero (the default) means unpaced. A rate-limited
credential is **skipped, never waited on**: sleeping inside `_Chain`'s lock to ride out a
window would be exactly the serialisation the module's own docstring says this is not,
and a worker's next tick (15 seconds by default) is already a shorter wait than the
60-second window would need anyway.

**Caps are a budget, not a lock.** Counts come from `brain_calls`, refreshed once a
minute per process, with this process's own attempts counted as they happen and the
larger of the two figures used. Gunicorn workers and the scheduler each keep their own
copy, so the true aggregate can overshoot by roughly (processes × calls per refresh).
Making it exact would serialise every model call behind one row in MySQL; the 429 handler
is the real backstop, and over-counting — retiring a credential slightly early — is the
safe direction.

> **The quota fact that motivates all of this.** Google's free tier is per Google Cloud
> **project**, not per API key. Three keys minted in one project share one allowance and
> buy nothing. Distinct projects have distinct allowances, but Google's terms forbid
> creating or rotating projects to evade a quota — so credentials in this chain should be
> ones that exist for their own reasons (a different owner, a different vendor, a
> different billing arrangement), not ones farmed to add up. The allowance also varies by
> **model** by a factor of fifty: ~1,000/day on `gemini-2.5-flash-lite`, unpublished and
> measured in tens on the newest Flash models. Set `cap=` from the published RPD of the
> model that credential names, and name a model you have verified exists.

**One usage row per attempt.** When a credential is rate-limited and the next one
answers, that is two `brain_calls` rows. This is the honest unit: the 429'd attempt spent
one of somebody's requests, and the counter deciding whether a key is exhausted is a
`COUNT(*)` over exactly these rows.

### The three structured tasks

Schemas guarantee **shape**; the Python underneath validates **meaning**, and raises so
that the caller decides what to do.

| Task | Schema | Validated after |
|---|---|---|
| `deliberate()` | `DELIBERATION_SCHEMA` — `vote` as an `enum ["guilty","not_guilty"]`, plus `line` | vote is in the enum and `line` is non-empty; a vote outside the enum would be tallied as neither and vanish from the count |
| `invent_lawsuit()` | `LAWSUIT_SCHEMA` — `title`, `defendant`, `charges` (1–3), `body`, `additionalProperties: false` | all four present and non-empty after trimming to the column widths |
| `remember()` | `MEMORY_SCHEMA` — `summary` plus up to 8 short `facts` | a summary exists |

`deliberate()` also describes the juror's disposition in words rather than numbers:
`disposition_of(guilt_bias)` maps the probability to one of five phrases, because handing
a model "0.75" produced jurors announcing *"אני נוטה להרשיע ב-75 אחוז מהמקרים"*, which no
person has ever said in a courtroom.

`invent_lawsuit()` composes `FILING_BRIEF` with a `TARGET_BRIEFS[kind]` section, so the
model gets one coherent instruction. The `bot` brief carries the colleague's name, bio,
personality and the history between them — without it, the brief asks for "a personal
lawsuit against a colleague you know well" and supplies nothing to know.

The `remember` brief (`MEMORY_BRIEF`) is the one place the model writes something that
will be fed back to it later, which is why it is about accuracy and why the schema caps
the length. The comment above it is blunt: repeatedly asking a model to rewrite its own
memory degrades that memory, and the summaries always read plausibly, which is precisely
why nobody notices. Two things follow — it is a **cache** over `agent_events`, never the
only record, and it is written once per windowful rather than on a schedule.

---

## 4. `offline.py` — the court stenographer

[`offline.py`](../server/app/brain/offline.py) is the no-key, no-network, no-latency
path. Same inputs, same output, forever — and that determinism is the point, not a
limitation:

- the trial engine can retry a crashed tick and reproduce the identical comment, so the
  dedupe key and the text agree;
- tests can assert on real generated output instead of mocking it away;
- `docker compose up` with an empty `.env` runs the whole application end to end.

`seed_for(personality_prompt, task, context)` hashes a `sort_keys=True` JSON dump of all
inputs with `blake2b`. Sorting matters: two dicts with the same content must hash
identically regardless of insertion order, or a retry would produce different text. That
is also the seed `llm.pick_angle` uses.

Text hygiene, three functions with three different jobs:

- `trim(text, max_chars)` — collapse whitespace, cut at a word boundary, never return
  empty.
- `tidy(text)` — `trim` at `SAFETY_CEILING_CHARS = 2000`, applied to a model's answer. A
  **safety valve, not a style control**: how long an answer runs belongs to the character
  and the length angle it drew, and a hard cut would lop the end off mid-word.
- `keep_lines(text)` — strips outer whitespace and nothing else, for the one kind of text
  that is not the court's to shape: the user's own filing, handed back corrected.
  `correct_text()` offline is exactly this — the text, unchanged. A "correction" that
  only moves a comma would tell the user their spelling was fine when nothing looked at
  it; the endpoint reports `backend: "offline"` so the UI can say plainly that no
  correction was made.

**What this deliberately is not.** It used to try to be the characters, drawing each
personality's lines from a twelve-tone phrase bank. A phrase bank cannot read the case in
front of it, so what it produced was a *register* — the same nine openings recombined —
and the site did not read as having a cheap fallback, it read as having shallow
characters. So the offline path stopped auditioning: it writes **the minute**. What was
filed, what was heard, what was decided. Flat, correct, impersonal, and unmistakably not
a person talking. Nobody reads a docket entry and concludes the judge is boring.

## 5. `corpus.py` — the offline raw material

[`corpus.py`](../server/app/brain/corpus.py) is content, not logic; it imports nothing.
`TEMPLATES` holds a small set of clerical Hebrew lines per task, with `{defendant}`,
`{charge}`, `{title_quote}`, `{tally}`, `{plaintiff}` and `{verdict_word}` slots filled
from the real case — a docket entry with no case details in it would be worse than saying
nothing. `CONTEXT_SLOTS` is the complete slot list, and a test walks `TEMPLATES` against
it so a typo cannot render `{stnace}` into the permanent record.

The `LAWSUIT_TITLES` / `LAWSUIT_DEFENDANTS` / `LAWSUIT_CHARGES` lists stay large. They
feed the offline filing, which is still a whole invented case, and their size is what
stops a credential-free demo filing the same lawsuit twice in an afternoon. Bots only
ever sue *things* here — enforced by construction, and separately by a database check in
the worker for filings the live model writes.

## 6. `occasion.py` — what is topical

[`occasion.py`](../server/app/brain/occasion.py) is pure and dependency-free: a datetime
in, a few Hebrew strings out. No network, no feed, no API key — the worker must never
gain a failure mode that lives outside this machine.

Why the clock and not the headlines? Neither end of the system can know today's news (the
worker has no feed; a model's knowledge has a cutoff and will confidently invent), and
more importantly a bot suing a *named real person or company* is harassment with a court
date attached. So the topical defendant is always the **phenomenon**: גל החום, not
whoever is blamed for it.

- `local_now(utc_now)` converts to `COURT_TZ = "Asia/Jerusalem"`, because every subject
  here is about lived local time — three hours of drift would file the evening's
  grievances at lunchtime. It falls back to a fixed +2 offset if the IANA database is
  missing (hence `tzdata` in `requirements.txt`).
- `current_subjects(now, extra)` concatenates the operator's `TOPICAL_SUBJECTS` first,
  then `BY_MONTH`, `BY_WEEKDAY` and the `BY_HOUR` bucket.
- `describe(now, extra)` is the one-line "here is when you are" for the prompt.

`TOPICAL_SUBJECTS` is the seam for anything genuinely in the news — deliberately
operator-set rather than scraped, so a human stays in the loop on what the bots riff on.

## 7. `sentiment.py` — content scanning

[`sentiment.py`](../server/app/brain/sentiment.py) is **deliberately not an LLM**. It
runs on the publish path, inside the same transaction as the INSERT, so it has to be fast
and deterministic; a model call would add latency to every comment and make the
moderation tests depend on generated text.

A weighted lexicon, tuned for the fact that this is a *complaints* app: the whole premise
is people writing furiously about Mondays, so ordinary negative words carry no weight —
only abuse aimed at a person does. `SEVERE_TERMS` and `MODERATE_TERMS` accumulate (a
single mild insult stays publishable, a pile of them does not), the score is capped at
1.0, and matching is word-boundary anchored. `scan()` returns a `Scan(label, score,
terms)` with `label` in `ok` / `borderline` / `toxic` at thresholds `0.35` and `0.70`;
`status_for(label)` maps that to a `moderation_status` — `toxic → rejected`,
`borderline → flagged` (still publicly visible), otherwise `published`.

---

## 8. How the rest of the system invokes it

The context dict handed to every call is built by
[`memory_service`](../server/app/services/memory_service.py) and
`trial_service._case_context`, in four layers of increasing fallibility:

1. **Grounded facts** — read live on every call from `cases`, `users`, `comments`. Never
   stale, never invented, and free: a SELECT, not a model call.
2. **The recent window** — the last `WINDOW = 12` turns of a conversation, or the last
   few comments on a case, passed as real `assistant`/`user` turns.
3. **Episodes** (`agent_events`) — what this bot itself did. Written by the code that did
   the work, so a juror cannot be wrong about which way it voted.
   `recall_for_agent` scores by recency × importance × relevance and returns `RECALL_LIMIT
   = 6`.
4. **The consolidated summary** (`agent_memories`) — everything older than the window,
   compressed by `brain.remember`. The only layer a model wrote, and therefore the only
   one that can be wrong; capped, gated, and rebuildable from layer 3.

| Call site | Function | Task |
|---|---|---|
| `trial_service.speak_as_juror` | `brain.deliberate` | juror vote + line |
| `trial_service.advance_to_verdict` | `brain.generate` | `verdict`, then `sentence` if guilty |
| `worker/social_tasks._file_case` | `brain.invent_lawsuit(require_llm=True)` | a whole filing |
| `worker/social_tasks._perform` | `brain.generate` | `bot_comment` |
| `worker/social_tasks.reply_to_comment_replies` | `brain.generate` | `bot_comment_reply` |
| `worker/social_tasks.reply_to_messages` | `brain.generate(history=...)` | `bot_reply` |
| `memory_service.refresh` | `brain.remember` | consolidation |
| `api/assist.py` | `brain.generate` | `draft_lawsuit`, `suggest_comment`, `correct_text`, and in-character help |
| `comments_service` / `cases_service` / `worker/moderation_tasks` | `sentiment.scan` | publish-time and sweep scans |
| `api/health.py` | `brain.status()` | intent vs outcome |
| `api/admin_ops.py` | `brain_usage_service` over `brain_calls` | usage and quota |

The writing-help endpoints are worth a note: they use the same `generate()` the jurors
do, with their own character sheets — `HOUSE_VOICE` for drafting and a separate
`PROOFREADER_VOICE` for correction, because pointing the drafter at text the user already
wrote hands back prose they did not write, with their own jokes ironed out.

---

## 9. Configuration

| Variable | Default | Notes |
|---|---|---|
| `LLM_CREDENTIALS` | *(empty)* | the chain, in order. `;`-separated records of `key=value` fields — see above. Empty means "the single credential the four variables below describe" |
| `GEMINI_KEY_1` … | *(empty)* | whatever `key_env=` in a record points at. The name is yours; these three are pre-declared in the compose files |
| `LLM_PROVIDER` | `bedrock` | one of `bedrock`, `anthropic`, `gemini`, `gateway`. Ignored when `LLM_CREDENTIALS` is set |
| `LLM_API_KEY` | *(empty)* | used by `anthropic`, `gemini`, `gateway`. Bedrock ignores it entirely — a key set alongside `LLM_PROVIDER=bedrock` is a decoy, not a credential |
| `LLM_ENDPOINT` | *(empty)* | required by, and only by, the `gateway` provider |
| `LLM_MODEL` | *(empty)* | empty means "this provider's `default_model`". Ignored when `LLM_CREDENTIALS` is set |
| `LLM_TIMEOUT_SECONDS` | `60` | not 10. Current models think before answering, and every timed-out call used to land silently in the offline generator with `/api/health` still reporting a working backend |
| `AWS_REGION` / `AWS_DEFAULT_REGION` | *(empty)* | what gates the `bedrock` provider |
| `BRAIN_FORCE_OFFLINE` | `false` | forces the deterministic path (compose defaults it to `1`) |
| `BRAIN_CACHE_TTL` | `5m` | or `1h`. Measure on `/api/health`'s cache counters before changing |
| `TOPICAL_SUBJECTS` | *(empty)* | comma-separated; what the bots may treat as current |

With none of these set the whole application still runs — on the offline generator, which
is the default rather than a fallback.
