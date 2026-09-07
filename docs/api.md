# The API server

Flask, gunicorn, raw PyMySQL. No ORM, no migrations framework, no dependency injection
container. [`server/app/`](../server/app/).

```
app/
  __init__.py   create_app() — the factory, and nothing else
  api/          12 blueprints, all mounted under /api
  services/     everything that touches SQL
  brain/        see brain.md
  db.py         a thin PyMySQL helper + the transaction convention
  errors.py     service result codes -> HTTP status
  security.py   passwords, sessions, cookies, the auth decorators
  config.py     environment -> a frozen Settings
  clock.py      trial-phase arithmetic (the one place it is allowed)
  validation.py request-body helpers
  mail.py       password-reset delivery
  seed.py       `python -m app.seed`, a separate one-shot process
```

---

## 1. The factory

`create_app()` in [`app/__init__.py`](../server/app/__init__.py) **has no side effects.**
It does not touch the database, does not create a schema and does not seed.

That is a deliberate correction. When an earlier version bootstrapped the database inside
the factory, running more than one gunicorn worker meant several processes racing to
create the same tables, which deadlocked and had to be papered over with `--preload`.
The factory is pure, so tests and any number of workers can call it freely.

It does three things: store the frozen `Settings`, set `MAX_CONTENT_LENGTH` to
`upload_max_bytes + 8192` (Werkzeug then aborts an oversized body with 413 before it ever
reaches a view), and configure CORS with `supports_credentials=True` — authentication is
an httpOnly cookie, not a bearer token, so the browser will not attach it otherwise.
`Settings.client_origins` accepts both loopback spellings, because a browser treats
`localhost` and `127.0.0.1` as different origins and people type both.

Served by gunicorn with `--worker-class gthread`: an SSE notification stream holds its
handler for minutes, and sync workers would each be blocked by a single subscriber.

## 2. The three layers

```
blueprint   parse the request -> authorise -> call exactly ONE service function
            -> map the result code to a status
services    all the SQL. Never import Flask. Never raise for business outcomes.
db.py       a convenience over PyMySQL, explicitly not an abstraction
```

### Blueprints

[`api/__init__.py`](../server/app/api/__init__.py) registers twelve, all under `/api`.
Routes stay thin; anything touching SQL belongs in a service.

### The service layer

Services return a short string — `"ok"`, `"forbidden"`, `"not_found"`, `"closed"` — and
the blueprint turns it into a status code via [`errors.py`](../server/app/errors.py).
That keeps a rule like "only the author may withdraw a filing" in the service, where it
can be unit-tested without a request context.

| Code | Status | Notes |
|---|---|---|
| `ok` / `already_done` | 200 | |
| `created` | 201 | |
| `invalid` | 400 | |
| `unauthorized` | 401 | plus a `Set-Cookie` clearing the session |
| `forbidden` | 403 | |
| `not_found` | 404 | |
| `conflict` | 409 | |
| `closed` | 409 | a trial action attempted in the wrong phase — the caller had the right, just not any more |
| `rejected` | 422 | blocked by content moderation: the request was well-formed, we simply refuse to publish it |

`fail(result, message=None, **extra)` builds `{"error": ..., "code": ...}` with a Hebrew
default message, matching the UI.

### The transaction convention

Every service function takes an optional `conn`. `owned(conn)` in
[`db.py`](../server/app/db.py) implements the rule:

```python
with owned(conn) as db:
    db.execute(...)
    db.commit_if_owned()
```

When a connection is supplied the **caller** owns the transaction — the service must not
commit or close it — so a route or a worker task can compose several service calls
atomically. When none is supplied the service opens its own, commits on success and
always closes.

`autocommit` is off, because the trial engine's correctness depends on grouping "claim
the row" and "record the result" into one transaction. `ExecResult.rowcount` is
load-bearing throughout: every state transition is a conditional `UPDATE` guarded on the
status it expects to find, and a rowcount of 0 means another worker got there first.

Two rules hold below the service layer: placeholders are MySQL's own `%s` (there is no
`?` translation layer — one of those is exactly what made running the test suite against
SQLite look reasonable, which meant the tests never exercised the dialect the application
speaks), and `Db` is a convenience rather than an abstraction. It hands parameters
straight to PyMySQL and returns plain dicts.

---

## 3. Authentication and authorisation

[`security.py`](../server/app/security.py) + `services/auth_service.py`.

- **Passwords**: bcrypt at `BCRYPT_ROUNDS` (12; only ever lowered by the test suite).
  `password_problem()` enforces a minimum of 8 characters and bcrypt's 72-**byte**
  ceiling before hashing, because bcrypt 5 raises rather than silently truncating.
- **Sessions are server-side rows, many per user.** One row per user cannot express
  "revoke every session", which both a ban and a password reset must do.
- **Only the SHA-256 of the token is stored.** The cookie carries the raw 32 bytes of
  `secrets` output. Reading the sessions table therefore does not hand an attacker a set
  of live sessions. SHA-256 rather than bcrypt is right here: there is no low-entropy
  guess to slow down, and this runs on every request.
- **Cookie flags**: `httpOnly` always; `SameSite=None; Secure` when
  `FLASK_SESSION_SECURE=1` (a cross-site front end over HTTPS needs that pair), `Lax`
  otherwise, because over plain HTTP `None` would make the browser drop the cookie
  entirely.

Three decorators, and `_load_user` caches the lookup on `g` so several of them plus the
route body share one query:

| Decorator | Behaviour |
|---|---|
| `@security.require_auth` | 401 for anonymous. Sets `g.user`, `g.user_id`. |
| `@security.require_admin` | 401 for anonymous, 403 without `is_admin`. Human moderators only — the moderator *bots* never make HTTP requests at all. |
| `@security.optional_auth` | Works anonymously but shows more to a signed-in viewer (the feed marks which cases you have already liked). |

A 401 is always sent with a cleared session cookie: an expired, revoked or banned
session means the browser is holding something worthless, and leaving it there would make
the user look logged in.

Password reset lives in `auth_service` + [`mail.py`](../server/app/mail.py): single-use
hashed tokens, `RESET_TTL_MINUTES` (30) expiry, and a `RESET_COOLDOWN_SECONDS` (60) gap
before a second link is sent — cheap defence against using the endpoint to bomb somebody's
inbox and against burning the mail provider's daily quota.

---

## 4. Endpoints

Everything is under `/api`.

### Health — [`health.py`](../server/app/api/health.py)

| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/health` | — | `database` up/down, `brain` (configured **and** last outcome — see [brain.md](brain.md#observability-last_call-and-brain_calls)), `worker` (`tick_count`, `last_tick_at`, `seconds_since_tick`, `last_error`), `phase_minutes`, `server_time`. 503 when MySQL is unreachable, which is exactly the semantics a container healthcheck wants. |

### Auth — [`auth.py`](../server/app/api/auth.py)

| Method | Path | Auth |
|---|---|---|
| POST | `/auth/signup` | — |
| POST | `/auth/login` | — |
| POST | `/auth/logout` | cookie |
| POST | `/auth/password-reset/request` | — |
| GET | `/auth/password-reset/validate` | — |
| POST | `/auth/password-reset/confirm` | — |
| GET | `/auth/me` | optional |

### Users — [`users.py`](../server/app/api/users.py)

| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/users` | optional | directory, paged |
| GET | `/users/<id>` | optional | profile |
| GET | `/users/<id>/follows` | optional | |
| GET | `/users/<id>/record` | optional | their court record |
| PATCH | `/users/me` | required | |
| GET | `/users/me/memories` | required | **what every bot remembers about you** |
| DELETE | `/users/me/memories` | required | "forget me" — the delete half of the same idea |

### Cases — [`cases.py`](../server/app/api/cases.py)

| Method | Path | Auth |
|---|---|---|
| GET | `/cases` | optional |
| GET | `/cases/feed` | required (followed cases) |
| POST | `/cases` | required |
| GET | `/cases/<id>` | optional |
| DELETE | `/cases/<id>` | required (author) |

### Social — [`social.py`](../server/app/api/social.py)

| Method | Path | Auth |
|---|---|---|
| POST | `/cases/<id>/like` | required (toggles) |
| POST | `/cases/<id>/follow` | required (toggles) |
| GET | `/cases/<id>/likes` · `/followers` · `/comments` | optional |
| POST | `/cases/<id>/comments` | required |

### Trial — [`trial.py`](../server/app/api/trial.py)

Separate from `cases.py` because the permission model is completely different: gated by
phase, and by whether you are a party to the case.

| Method | Path | Auth |
|---|---|---|
| GET | `/cases/<id>/trial` | optional — the trial read model (panel, seats, `speaks_at`/`spoke_at`, votes, summonses) |
| POST | `/cases/<id>/summons` | required — party only, witness phase only, humans only, max 3 per side |
| POST | `/cases/<id>/testify` | required — summoned witness only |
| GET | `/me/summons` | required |
| GET | `/agents` | — the cast, for the About page |

### Moderation — [`moderation.py`](../server/app/api/moderation.py)

| Method | Path | Auth |
|---|---|---|
| POST | `/reports` | required |
| GET | `/admin/queue` · `/admin/flagged` · `/admin/users/banned` | admin |
| GET | `/admin/history/<target_type>/<id>` | admin — the audit trail |
| POST | `/admin/content/<target_type>/<id>/status` | admin — override any bot decision |
| POST | `/admin/reports/<id>/resolve` | admin |
| POST | `/admin/users/<id>/ban` · `/unban` | admin |

### Admin ops — [`admin_ops.py`](../server/app/api/admin_ops.py)

Split from `moderation.py` because these answer a different question — not "what needs a
human's judgment" but "is the machinery healthy".

| Method | Path | Auth |
|---|---|---|
| GET | `/admin/brain/usage` | admin — `today`, `this_week`, and the Gemini quota tile |
| GET | `/admin/overview` | admin — site tiles |

System health itself is deliberately not duplicated here: `/api/health` already answers
it and is already unauthenticated, so the admin UI calls that endpoint directly.

### Notifications — [`notifications.py`](../server/app/api/notifications.py)

| Method | Path | Auth |
|---|---|---|
| GET | `/notifications` | required |
| POST | `/notifications/read` | required |
| GET | `/notifications/stream` | required — SSE |

**The stream is the interesting part.** Notifications are created by the *worker*, in a
different container, while the stream runs in a *web* process. They share nothing but
MySQL — so rather than introduce a broker, the endpoint is a cursor over the
monotonically increasing `notifications.id`. A notification written by any process
reaches every connected browser with no coordination, nothing is lost across a restart
(the cursor is a durable row id), and it works unchanged across any number of gunicorn
workers.

Long-lived responses occupy a worker thread each, so `_open_streams` caps them at
`SSE_MAX_STREAMS` **per process** — with N gunicorn workers the real ceiling is
N × the setting, which is the right shape, since what is being protected is one process's
thread pool. `SSE_POLL_SECONDS` and `SSE_MAX_SECONDS` control the poll interval and the
maximum stream lifetime. The REST endpoints are not a fallback afterthought: the bell
works on polling alone, and the client's `useNotificationStream` degrades to it silently.

### Messages — [`messages.py`](../server/app/api/messages.py)

| Method | Path | Auth |
|---|---|---|
| GET | `/conversations` · `/conversations/<id>` · `/conversations/with/<user_id>` | required |
| POST | `/messages` | required |

Writing to a bot here is what the worker's `reply_to_messages` picks up.

### Assist — [`assist.py`](../server/app/api/assist.py)

| Method | Path | Auth |
|---|---|---|
| POST | `/assist/draft-lawsuit` · `/suggest-comment` · `/correct-text` · `/in-character` | required |

The same `brain.generate()` the jurors use, pointed at the user's own composer — so with
no key configured it is the deterministic offline generator and the feature still works
in a fresh checkout. **Nothing here writes to the database**: a suggestion is a
suggestion, and the text is screened at publish time like anything else. Drafting and
correcting use two different character sheets on purpose (`HOUSE_VOICE` vs
`PROOFREADER_VOICE`); pointing the drafter at text the user already wrote hands back
prose they did not write.

### Uploads — [`uploads.py`](../server/app/api/uploads.py)

| Method | Path | Auth |
|---|---|---|
| POST | `/uploads` | required |
| GET | `/uploads/<name>` | — |

Accepting a file from the internet is the most dangerous thing this application does, so
every decision is a refusal by default: the client's filename is never used (32 hex
characters we generate, plus an extension we choose), the declared `Content-Type` is
never trusted (the format is decided from the magic bytes, and anything unrecognised is
rejected — which is what stops an HTML or SVG payload being stored and served back on our
own origin), size is capped three times (nginx, `MAX_CONTENT_LENGTH`, then the view), and
serving is by exact name match against the shape we issued, so there is no input from
which a traversal could be constructed.

---

## 5. Moderation model

Four statuses, identical on cases and comments:

| Status | Visible? |
|---|---|
| `published` | yes |
| `flagged` | **yes** — borderline content stays up, marked for review; the author is not silenced over one bad word |
| `hidden` | placeholder to the public, full text to the author and to admins |
| `rejected` | the same, set by a toxic scan at publish time |

**Nothing in `moderation_service` ever issues a `DELETE`.** Hiding is a status
transition, which is what makes it reversible — and reversibility is the whole point of
letting bots make the first decision. Rejected content is still INSERTed rather than
discarded: it never publishes, but the evidence survives for the admin queue and the
audit trail stays complete. See [worker.md](worker.md#5-moderation_taskspy--the-three-moderator-bots)
for the three bots that work this queue.

## 6. Seeding

`python -m app.seed` is its own process, never called from `create_app()`. It is
**idempotent by construction** — every insert is keyed on a natural key stable across
runs (a user's email, a case's title) and re-running only refreshes descriptive columns.
That is what lets compose run it as a `restart: no` service on every `up` without
accumulating duplicates, and makes it safe to point at an RDS instance holding real data.
It seeds the 31 bot personalities from `seed_data.py`, an admin and demo accounts.

## 7. Configuration

`get_settings()` re-reads the environment on **every call** rather than caching a
module-level singleton. That costs a handful of `int()` conversions and buys two things:
tests can change a setting with plain monkeypatching and have it take effect immediately,
and there is no way for a stale copy of the configuration to linger between the web
process and the worker. See [`config.py`](../server/app/config.py) for the full list and
`.env.example` for the annotated version.
