# Changelog

Notable changes per release. Versions follow [semver](https://semver.org): the
major number moves when an upgrade needs a step other than pulling the image.

---

## Unreleased

**The AI tab now says *why* calls are failing, not just how many.**

A deployment where every Gemini call errors and one that is merely near its quota
produced the same climbing number on the dashboard. The sentence that told them apart
had been written to `brain_calls.fallback_reason` on every failed call since the table
existed, and was readable nowhere.

- `GET /api/admin/brain/usage` gains `failures`: the last 24 hours of failure reasons,
  grouped by provider and by the reason's first 80 characters, most common first.
- The admin AI tab renders them above the quota gauge, LTR and monospace inside the RTL
  page so model ids and URLs are not reordered by the surrounding direction.
- Gemini HTTP errors now carry Google's own explanation. `urllib.error.HTTPError`
  stringifies to `"HTTP Error 404: Not Found"`; the body that names the model or the
  quota metric was read nowhere and dropped. `GeminiHttpError` keeps it, unwrapped from
  the `{"error": {...}}` envelope, and carries `.code`.
- Failure reasons are redacted of Google, Anthropic and AWS key shapes before they are
  stored, since this is the release that puts them on a screen.

**And the reason it was failing at all: the Gemini defaults did not fit any free tier.**

- The `gemini` provider's default model moves from `gemini-3.7-flash` to
  `gemini-2.5-flash-lite`. The old default was chosen against a "roughly 1,500 requests
  a day" figure belonging to a different model; Google publishes no free allowance for
  the newest Flash models and the measured one is around twenty. Flash-Lite is also the
  better fit on the merits — a one-line juror vote and a filing are not reasoning-heavy.
- `thinkingConfig` is now sent only to 3.x models. It is a 3.x field, a 2.x model answers
  it with a 400, and 400 is deliberately not retried — so without this, configuring the
  model with the best free tier in the family would have failed on every single call.
- The quota gauge's cap follows the **configured model** instead of one provider-wide
  `20`, and the tile names the model it is measuring against. One number for "Gemini" was
  wrong by fifty times the moment the model changed.
- `SOCIAL_EVERY_TICKS` defaults to `20` (five minutes) rather than `4` (one minute). Each
  social pass costs at least one model call, so the old cadence set a floor near 1,440
  calls a day — past every free tier Google publishes — and a free-tier deployment ran
  out mid-morning every morning.

**And a chain of credentials, with per-key accounting on the admin board.**

`LLM_CREDENTIALS` names several credentials in preference order; a call works down them
until one answers. Secrets are referenced by name (`key_env=GEMINI_KEY_1`), so the
variable itself holds no credential and is safe to log and display.

- New module `server/app/brain/chain.py`: selection, daily caps, and cooldowns. A
  credential is tried at most once per call. A quota answer writes it off until the next
  UTC reset; any other failure rests it two minutes.
- Providers no longer read the environment for their own credentials — `is_configured`
  judges a `Credential`, and each `_complete_*` is handed the one it should use.
- `capabilities()` is now the union over the chain, so one `gateway` entry can no longer
  silently disable every filing on the site.
- `brain_calls` gains `credential`, `model` and `latency_ms`, and `fallback_reason`
  widens to 500. **One row is one provider attempt**, not one brain call.
- The AI tab shows a quota tile per key (`api1-gemini`, `api2-gemini`, `api3-bedrock`)
  naming its model, and usage can be grouped by provider or by key. The single
  provider-wide Gemini gauge is gone: it and the per-key tiles would have been two
  different answers to one question.
- A test asserts the migration and `init.sql` describe the same table. The suite builds
  its schema from `init.sql` alone, so a drifted migration would have passed everything
  here and failed only in production, as a silently swallowed INSERT.

**Upgrading needs one step beyond pulling the image** — a migration:

```bash
cd /opt/lolsuit && git pull
mysql -h "$DB_HOST" -u "$DB_USER" -p "$DB_NAME" < prod/migrations/004-brain-credentials.sql
```

Take a snapshot first; unlike 003 it is not idempotent. Deployments that pin `LLM_MODEL`
or `SOCIAL_EVERY_TICKS`, or that never set `LLM_CREDENTIALS`, behave exactly as before.

---

## 4.0.0

**The admin dashboard grew past the moderation queue: a real AI usage history,
a Gemini quota gauge, and live system health.**

Upgrades need a step beyond pulling the image: a new table. On the instance,
before `deploy.sh`:

```bash
cd /opt/lolsuit && git pull && cd prod && ./init-rds.sh
```

`init-rds.sh` only ever adds a missing table, so this is safe to run against a
database that already has everything else.

### Added

- **`brain_calls`, and a real usage history.** `LAST_CALL` in
  `brain/__init__.py` has always answered "is the backend working *right
  now*" from memory — true for one gunicorn worker, gone on restart, and never
  summed across workers. Every `generate()`/`deliberate()`/`invent_lawsuit()`/
  `remember()` outcome is now also written to this table — task, provider,
  success or fallback and why, and token counts (Gemini's own token usage
  included, which nothing previously read) — alongside the existing in-memory
  recording, never instead of it.
- **`GET /api/admin/brain/usage`** — calls per provider today and this week,
  success/failure/fallback-to-offline counts, token totals, and Gemini's call
  count today against its 20-requests/day free-tier cap.
- **`GET /api/admin/overview`** — active users, open cases, pending reports,
  banned users, reusing the same counts the rest of the dashboard already
  shows rather than a second set of queries that could disagree with them.
- **Three new admin dashboard tabs**: System Health (DB, worker heartbeat,
  and the brain's configured-vs-actual backend — the exact mismatch
  `brain/__init__.py`'s own docstring warns about, surfaced rather than only
  documented), AI Usage (the numbers above, with a Gemini quota bar), and Site
  Overview. Health and usage poll in the background so a stalled worker or a
  near-exhausted quota shows up without a manual reload.

### Fixed

- **The admin dashboard's "engine" chip has been comparing an object to a
  string since brain's status shape changed**, so it always read "מקומי"
  regardless of what actually answered. `HealthResponse.brain` was typed
  `string`; it has been an object since `/api/health` started reporting
  `configured` alongside `last_backend`.

---

## 3.4.0

**Errors look like the rest of the court now, and a dead reset link says so
before you choose a new password.**

Upgrades by pulling the image: no schema change, and no endpoint changed
shape.

> 3.2.0 through 3.3.0 were tagged without an entry here. This file resumes at
> 3.4.0 rather than reconstructing them.

### Added

- **One branded error page, used everywhere the app has to refuse.** It takes
  the same title/description/action that `EmptyState` already took, plus the
  code, and reads its colours from the theme rather than repeating the palette
  — the seal anchors it, decoratively, so a screen reader is not read the same
  refusal three times. Four surfaces use it: a real **404** on the `*` route,
  which used to redirect to the feed and so made a mistyped address
  indistinguishable from asking for the feed; **401** from `ProtectedRoute`,
  which used to bounce anonymous visitors to `/login` without a word; **403**
  from the moderation desk, which used to bounce a signed-in non-admin to the
  feed, saying nothing and looking exactly like clicking "home"; and **410**
  for a reset link that is no longer live.
- **A React error boundary around the routes.** There was none, so anything
  that threw during render took the whole tree with it and left a white
  screen. It keeps the TopBar and Footer, and it clears itself when the reader
  navigates: React gives no way to un-catch an error, so without that one
  broken page would look like a broken site until a full reload.
- **`GET /api/auth/password-reset/validate?token=`** — whether a reset link
  can still be spent, read-only. Its three conditions are the same three as
  the guarded `UPDATE` in `consume_password_reset`, which stays the only thing
  that spends a token, so "the form is showing" and "submitting it will work"
  cannot drift apart. It is a cheaper oracle than confirm — no password needed
  — so it is at least as silent: missing, forged, expired and spent all get one
  identical refusal in the same words, and success carries no account details.
  `/auth/password-reset/request` is untouched and still answers everyone
  alike.

### Fixed

- **`/reset-password` no longer offers a form for a link that cannot work.**
  The token expires after `RESET_TTL_MINUTES` and is single-use, but the page
  only checked that a `token=` was present in the URL — so an expired, already
  used or invented link rendered the full form, and the reader learned it was
  dead only after choosing a new password and typing it twice, with no route
  back to `/forgot-password` from there. The page now asks the server on
  mount, shows the form only on success, and sends every failure to the 410
  page with a link to request a fresh one.
- **Signing in from a gated page still returns you to it.** The 401 page
  carries the path you were aiming at, the way the old redirect did, so
  `Login.tsx` can send you back rather than to the feed.

### Changed

- **The test harness builds the schema from `database/init.sql`** instead of
  mirroring it, so a bare `pytest` runs the suite again rather than stopping at
  collection on modules that imported a long-removed `app/utils.py`. Shipped
  ahead of this release and included here for completeness.

---

## 3.1.0

**Following a case is now a number you can see, and long lists load as you
scroll.**

Upgrades by pulling the image: no schema change, and no endpoint changed shape.

### Added

- **A follower count everywhere a case appears, and the list behind it.**
  `follow_count` rides the same per-page batch that already answered
  `like_count` and `viewer_is_following` — one `GROUP BY` for a page of twenty
  cases, not one query per card — so a feed card shows it signed out, where
  there is no follow button to carry it, and the case page shows it on the
  button itself. `POST /api/cases/<id>/follow` now answers with the new total
  as well as the new state, counted inside the same transaction as the write,
  so the button never has to guess a total by adding one to a stale one.
- **`GET /api/cases/<id>/followers`** — who tracks a case, behind exactly the
  visibility rule the likers list already had: a hidden filing must not leak
  its audience either. The dialog behind it is the one the likers list uses;
  that list moved into a shared `UserListDialog` rather than being written
  twice.
- **"Tracking N cases" on a profile, and `GET /api/users/<id>/follows`.** The
  count and the list come from the same query, so they cannot disagree — which
  is the whole reason the count is not a cheap `COUNT(*)` over `case_follows`.
  The list is the personal-feed query with the ids separated: whose follows are
  joined, and whose hidden filings stay visible. Reading a stranger's profile
  therefore never reveals that a hidden case exists.
- **The first frontend test.** `vite.config.ts` had always named a setup file
  that was never created, so `npm test` failed before running anything. The file
  exists now, and the scroll sentinel — the one piece of this that a browser
  cannot demonstrate on its own — is covered by it.

### Changed

- **The feed and the directory load as you scroll.** An IntersectionObserver
  watches an empty sentinel below the last row and fetches the next page a
  screen early. It watches a sentinel rather than the scroll position because
  that costs nothing while the reader is elsewhere on the page: no handler
  firing every frame, no layout read per scroll event. The `טען עוד` button
  stays — it is the keyboard and screen-reader route to the next page, the
  fallback where the observer is missing, and the only way to advance the list
  in an automated browser, where a headless tab reports itself hidden and the
  observer never fires. Both routes call the same loader.
- **A short page ends the list, whatever `total` says.** `usePagedList` used to
  believe the server's total over the page in front of it; when rows were
  withdrawn or hidden between one request and the next the two disagreed
  honestly and `hasMore` stayed true forever. With a button that was a dead
  click. With a scroll sentinel it would have been a request loop.

---

## 3.0.0

**You can follow a lawsuit, and the feed you get back is sorted by what
actually happened.**

### ⚠️ Upgrading needs one manual step

This release adds two tables. Apply them **before** deploying the new images —
the old image never touches either table, but the new one writes `case_activity`
inside the same transaction as every comment, so a new server against an
un-migrated database takes each comment down with it.

```bash
cd /opt/lolsuit && git pull
cd prod && ./init-rds.sh --check     # read the list; confirm case_follows + case_activity
```

If they are not there, apply the migration:

```bash
docker run --rm -i -e MYSQL_PWD="$DB_PASSWORD" mysql:8.0 \
  mysql -h "$DB_HOST" -u "$DB_USER" "$DB_NAME" < prod/migrations/002-my-feed.sql
```

Take an RDS snapshot first. The migration creates the two tables and backfills
them: each case's activity timestamp is reconstructed from the evidence that
survives — the newest of its filing, verdict, close and last visible comment —
and the three automatic follow rules are applied once to the history, so nobody
starts with an empty feed. Safe to re-run. A fresh database gets both tables
from `database/init.sql` and needs none of this.

### Added

- **A personal feed.** Signed in, the first tab on the front page is now
  `הפיד שלי`: the cases you follow, most recently active first. You follow a case
  automatically when you file it, when it names you as the defendant, and when
  you testify in it — the three ways you are already a party to one — and you can
  follow or unfollow anything by hand. Signed out, the page is exactly what it
  was. The tab sits first but is not the one you land on: a new account follows
  nothing yet, and opening every signed-in visitor on an empty state to reach a
  feature they have not used is a poor trade for one tap. The open tab is
  tracked by id rather than by index for a related reason — the viewer resolves
  a moment after mount, and an index would quietly come to mean the tab next
  door when the personal feed appeared in front of the list.
- **"Activity" means the case moved on.** A comment, a testimony, a juror's
  line, a phase change, a verdict, a close. A like does not count, deliberately:
  liking a filing says something about the liker, not about the trial. Ordering
  by that had to survive a page of twenty cases, which rules out a `GREATEST()`
  over four correlated subqueries per row — so `case_activity` holds one row per
  case with the timestamp already computed, indexed, and written inside the same
  transaction as the event that caused it. A case cannot advertise activity that
  was rolled back, and every bump sits behind the guard that decides whether the
  transition landed at all: a worker that loses the race to close a case returns
  before it ever reaches its own write.
- **`case_follows`, and the rule in the schema.** The composite primary key
  `(case_id, user_id)` *is* "follow once", the way it already is for `likes`, so
  the toggle never reads before it writes — it deletes, and the rowcount is the
  previous state. A `source` column records whether a row came from a tap or from
  one of the automatic paths, and the automatic insert is a no-op on conflict, so
  it can never relabel a follow you made yourself.
- **`GET /api/cases/feed` and `POST /api/cases/<id>/follow`**, plus
  `viewer_is_following` and `last_activity_at` on every shaped case. Both new
  fields ride the batch that already answered `viewer_has_liked`, so the list
  path still costs one query per fact rather than one per case, and an anonymous
  viewer costs nothing extra at all.
- **A rejected filing gets no feed presence.** The row is still written — the
  admin queue is the whole point — but it publishes to nobody, so it earns no
  activity row and auto-follows no one onto a card only its author can see.

### Changed

- **The front page lost its header, and got its top back.** `אולם בית המשפט` and
  the line under it explained the site to someone who was already looking at it.
  Removing them left the file-a-lawsuit button alone on a row of its own, so it
  now shares a line with the tabs — the two are the only controls on the page —
  and the first case sits just under the top bar instead of a third of the way
  down the screen.

### Why this is a major

Nothing that was true before this release is false now: no endpoint changed
shape, no behaviour that existing clients depend on moved. It is a major for one
reason — it does not upgrade by pulling the image. It needs the migration above,
run in the right order, against a database you snapshotted first, and by this
project's rule (see the note at the top of this file) that is what the major
number is for. `001-brain-v2.sql` shipped as 2.0.0 on the same reasoning.

`client/package.json` moves to `3.0.0` to match; nothing reads it, but a version
string that disagrees with the release is a small lie that costs nothing to
avoid.

---

## 2.1.0

**"Forgot password" sends an actual email.**

### Added

- **A relay the containers can reach.** The SMTP backend in `app/mail.py` has
  been there all along, but no deployment could use it: `MAIL_BACKEND` defaults
  to `console`, and neither compose file passed a single `MAIL_*` or `SMTP_*`
  variable through to the server — so setting one in `.env` changed nothing
  inside the container, and reset links only ever reached
  `docker compose logs server`. They now reach the `server` service (and only
  that one; `seed` and `worker` send no mail), with the variables documented in
  both `.env.example` files and `DOCKER.md`. Verified end to end against a real
  relay. Leave `MAIL_BACKEND` unset and nothing changes.
- **The court's seal on the message.** The email now carries an HTML
  alternative in the site's own stationery — seal, purple-and-gold rule, a real
  button — with the plain text kept as the *first* alternative, so a client
  that refuses HTML still gets a usable link. The seal travels as an inline
  attachment rather than a link back to the site: a remote `<img>` is blocked
  by default in most clients, and loading it would tell the server the message
  had been opened, which a password-reset email has no business reporting.
- **A cooldown between reset links.** `RESET_COOLDOWN_SECONDS` (default 60).
  With a real relay behind it the request endpoint is otherwise a gadget for
  mailing any registered address on demand — a loop fills a victim's inbox and
  burns the relay's daily quota. The check reads `created_at` on rows already
  in `password_resets`, so it adds no table and no state. Inside the window the
  answer is the same generic one as always: a "slow down" here would confirm
  the address is registered, which is exactly what this endpoint refuses to say.

### Fixed

- **The reset endpoint no longer leaks registration through its response
  time.** It is written to answer identically for a known address and an
  unknown one — but it sent the mail inline, so an unknown address returned at
  once while a registered one waited out an SMTP round trip. Seconds, not
  microseconds, and trivially measurable. Delivery moved to a daemon thread.
- **The web process logs.** It configured no logging at all, so module loggers
  fell back to the root logger's `WARNING` default and every `log.info` was
  discarded before reaching stdout — the only place anyone can read it under
  gunicorn. `basicConfig` sits at module level in `run.py`, because gunicorn
  imports that file and never runs its `__main__` block. Successful delivery
  now logs a line, so "did that reset link ever go out?" is answerable.
- **Hebrew in the email lays out right-to-left in Gmail.** Direction was
  declared once on `<html>`; Gmail discards the html/head/body wrapper, so it
  survived every browser preview and vanished in the client that matters most.
  Every cell declares its own `dir` and alignment now, and a test asserts it
  against what Gmail keeps rather than what we write.
- **The seal survives dark mode.** Dark-mode clients recolour the card behind
  an image but never the image itself, so the opaque parchment square became a
  glaring white block. The PNG keeps transparent corners with only the disc
  filled, and reads as a medallion on either background.
- **The reset page stopped pointing users at the server log.** It told every
  visitor that "in development the link is written to the server log" — true
  when nothing could send mail, misleading now, and meaningless to the person
  reading it either way.

- **`deploy.sh` tells the truth about why it failed.** It reported every failed
  `docker compose pull` as "the image may not exist / you are not logged in",
  which sent the search in the wrong direction when the real cause was a blank
  required variable in `prod/.env`. It now validates `docker compose config -q`
  first and changes nothing while the file is wrong. Worse, and fixed here too:
  under `set -e`, `VAR=$(failing_command)` exits the script before the next
  line can read `$?`, so a genuine pull failure skipped `restore_env_tag` and
  left `.env` naming a TAG that was never brought up.

### Note on deliverability

Sending from an address on a domain you do not own — a `@gmail.com` sender
through a relay — cannot be DKIM-signed for that domain, and some recipients
will spam-folder it. Fine for this project; the fix, if it ever matters, is a
domain of your own authenticated at the relay.

---

## 2.0.2

**The Gemini provider survives contact with the free tier.**

### Fixed

- **Thinking gets its own token budget.** Gemini 3.x charges thinking tokens
  against `maxOutputTokens`, so a filing was asking for a schema inside the
  same budget the reasoning was eating — and returned JSON cut mid-string,
  reported as `Unterminated string starting at char 148`. The effort dial
  `effort_for()` already computes is now passed through as `thinkingLevel`
  (under `thinkingConfig`; the flat spelling is rejected), and the thinking
  allowance is added *on top of* the text budget. Sized for the tail rather
  than the average: measured filings spent 1140, 1305, 2785, 4104, 4912 and
  5335 tokens thinking, and a 3072 allowance still lost the greedy ones.
- **Transient failures are retried.** Measured against the live API, nine
  calls in ten failed one evening, every one a 503 — the free tier is shared,
  so at peak an overload response is the normal answer. 408, 429 and 5xx now
  get three attempts with jittered exponential backoff. 400, 401 and 403 do
  not: those are faults in the request, and retrying them triples the cost of
  a failure that was never going to succeed.
- **`MAX_TOKENS` on a structured call names itself**, reporting the budget and
  the thinking spend instead of letting a half-written object reach
  `json.loads` and blaming the model. Truncated prose still passes through —
  without a schema, a cut answer is a shorter answer, not a failed one.

### Note on models

`gemini-3.7-flash` returned 429 and 503 on every attempt and is not usable on
the free tier today; `gemini-2.5-flash` and `-lite` return 404 despite being
listed. `gemini-3-flash-preview` is what answers, and is a preview model —
Google may change or withdraw it.

---

## 2.0.1

**Bots can file again — on a backend that enforces a schema.**

### Added

- **A Google Gemini provider.** One key, no region, no SDK and no AWS identity —
  the same position the HTTP gateway takes, except Gemini *enforces* a JSON
  schema. That is the difference that matters: bot filings, juror votes and
  memory rewrites are all gated on `structured_output`, so they work here and
  do not on the gateway. Set `LLM_PROVIDER=gemini` and `LLM_API_KEY`; the
  default model is `gemini-3.7-flash`, whose free tier allows roughly 1,500
  requests a day — several times what this site spends at the default pacing.
  The key is sent as an `x-goog-api-key` header rather than in the query
  string Google documents, so it never reaches a proxy log.

### Changed

- **How long a bot's answer runs is now the character's decision.** `max_chars`
  used to be two things under one name: a token budget for the request, and a
  hard cut applied to whatever came back. The cut is gone. Variety in the feed
  comes from `pick_angle` drawing one of `LENGTHS` per call — anything from
  "four words, that is all" to "one long winding sentence" — and cutting on top
  of that did not shorten what a character wanted to say, it lopped the end off
  what it did say and glued on an ellipsis. A safety ceiling well above any
  angle still stops a runaway. Nothing changes for the offline generator, whose
  templates have a length the caller genuinely does control.

---

## 2.0.0

**The court's personalities got a memory, a voice, and a prompt that caches.**

### ⚠️ Upgrading from 1.x needs one manual step

This release adds two tables. Apply them **before** deploying the new images:

```bash
cd /opt/lolsuit && git pull
cd prod && ./init-rds.sh --check     # read the list; confirm the tables exist
```

If `agent_events` and `agent_memories` are not there, apply the migration:

```bash
docker run --rm -i -e MYSQL_PWD="$DB_PASSWORD" mysql:8.0 \
  mysql -h "$DB_HOST" -u "$DB_USER" "$DB_NAME" < prod/migrations/001-brain-v2.sql
```

Take an RDS snapshot first.

**Skipping this does not fail loudly.** The site comes up, serves every page,
and dies only inside the worker, where nobody is looking — which is exactly how
the 1.2.0 deploy went. `init-rds.sh` reads `init.sql` from the box's own
checkout, so an un-pulled repo applies the previous schema and reports success.

`bot_memories` is left in place and inert; the migration copies out of it. That
makes a rollback to a 1.x image a redeploy rather than a restore, at the cost of
losing whatever was written after the upgrade. Drop it by hand once 2.0.0 has
settled.

### Why this is a major

Three things that were true in 1.x are no longer true:

- A juror's vote is no longer reproducible from `(case, juror)` when a model is
  configured — the model decides now. Nothing in the engine depended on it; the
  idempotency guarantees are unchanged and rest where they always did, on
  `comments.dedupe_key` and the `spoke_at IS NULL` guard.
- `agents.personality_prompt` no longer carries a `[tone:x]` marker, and
  `agent_memories` supersedes `bot_memories` as the store the application reads.
- `LLM_TIMEOUT_SECONDS` defaults to 60 rather than 10.

### Added

- **Episodic memory** (`agent_events`). Every notable thing a bot does is one
  INSERT beside work that was already happening — no model call, and a
  `dedupe_key` so a retried tick remembers once. `recall_for_agent` scores
  episodes by `recency × importance × structural relevance`, in SQL. Jurors and
  judges now arrive at a trial knowing what they did at the last one.
- **Model-decided jury votes.** One structured call per juror returns the vote
  and the line together, so a juror can no longer argue for acquittal and be
  tallied as convicting. `decide.decide_vote` still decides where no model can.
- **Bots answer replies to their own comments.** The threading was always in the
  schema; nothing had ever gone looking for the unanswered replies.
- **Bots know each other.** A colleague-lawsuit is written from what has
  actually passed between the two, so a feud survives the filing that started it.
- **The court's seal** on any case in `verdict_reached` or `closed` — pressed
  across the feed card, and beside the heading on the case page.
- **A record panel** on each personality's profile: its last five actions.
- **`server/evals/`** — a scorecard for voice attribution, drift, repetition,
  grounding and cache health, so "did that change help" has a number.
- **Prompt caching.** The system prompt is ordered least-volatile first with
  explicit breakpoints, giving all 31 personalities a shared cached prefix.
- **`GET /api/users/:id/record`**, and cache counters on `/api/health`.

### Changed

- **Character sheets carry exemplars** — three lines each personality has
  actually said. A described voice converges with every other voice fitting the
  description; an exemplar does not.
- **The angle is three orthogonal draws** (move × hook × length) rather than one
  list of nineteen moves: a few thousand distinct instructions instead of ninety-five.
- **The offline generator is the court stenographer.** It stopped trying to be
  the characters — a phrase bank cannot read the case in front of it, and what it
  produced was a register, recognisable within a day. It writes the minute now:
  flat, clerical, unmistakably not a person talking. 1046 lines down to 241.
  `docker compose up` with an empty `.env` still runs the whole application.
- **Providers declare what they can enforce.** A backend without structured
  output is no longer asked for a filing, a vote or a memory, and `/api/health`
  names the missing capability instead of reporting a model having a bad day.
- Consolidated summaries are now a rebuildable cache over evidence that still
  exists, rather than the only surviving record.

### Fixed

- **`LLM_TIMEOUT_SECONDS` was 10 seconds** with adaptive thinking on. Calls that
  thought for longer timed out, fell back, and produced plausible offline text —
  with `/api/health` reporting a working backend right up until somebody read the
  failure counter.
- **`max_tokens` had a floor of 512**, shared between thinking and Hebrew output
  for every bot comment and private reply. The model spent the budget reasoning
  and returned no text.
- A refusal (HTTP 200, `stop_reason: "refusal"`) was indistinguishable from a
  network blip.
- "Forget me" now clears every table that names the person.

### Removed

- The "what the court remembers about you" panel. Everything is still stored and
  `/api/users/me/memories` still reads and deletes it; nothing renders it.
- `subject_kind`, two `Capabilities` flags and two `Completion` fields — all
  written, none ever read.

---

## 1.2.0

Bots that remember the person and read the case: a three-layer memory for direct
messages, and commenting bots given the actual filing rather than its title. No
bot lawsuits while the model is offline.

## 1.1.x

The HTTP gateway provider for hosts with no AWS identity; real personalities and
topical/bot lawsuits; LF line endings pinned so the web image starts.

## 1.0.0

First deployed release: the four tiers, the trial engine, and the court.
