# Running LolSuit with Docker

Everything — frontend, API, trial scheduler and MySQL — comes up with one command.

```bash
docker compose up --build
```

Then open **<http://localhost:8080>**.

No `.env` is required **for the compose stack**: every variable has a working default in
`docker-compose.yml`. (Running the server *outside* Docker is different — there `.env`
is required; see [README.md](README.md#running-locally-without-docker).) See
[Environment variables](#environment-variables) for what to set and when, and
[docs/configuration.md](docs/configuration.md) for the full reference.

---

## What comes up

| Service | Image | Port | Role |
|---|---|---|---|
| `db` | `mysql:8.0` | `127.0.0.1:3307` | MySQL 8. Schema applied from `database/init.sql` on first boot. |
| `seed` | `lolsuit/server` | — | One-shot. Inserts the 31 court bots, the admin, the demo accounts and the opening case, then exits 0. |
| `server` | `lolsuit/server` | `127.0.0.1:5002` | Flask API under gunicorn. |
| `worker` | `lolsuit/server` | — | The trial scheduler. A separate process by design. |
| `web` | `lolsuit/web` | **`8080`** | nginx: serves the built bundle, reverse-proxies `/api`. |

`server`, `worker` and `seed` are three commands over **one image** — they share every
dependency, so building three would only mean three caches to invalidate.

### Start-up order

Compose enforces it with conditions, not with `sleep`:

```
db (healthy) ──> seed (exits 0) ──> server (healthy) ──> web
                              └───> worker
```

`db` is not "healthy" until it answers over **TCP**, which MySQL only does *after*
`init.sql` has been applied — during initialisation it listens on a unix socket
only. That is what stops the API from ever starting against a half-built schema.

### Only one port is public

`web` publishes `8080` on all interfaces. The API (`5002`) and MySQL (`3307`) are
bound to `127.0.0.1` — they exist for `curl`, Postman and the pytest suite, not for
the browser, which reaches the API through nginx.

---

## Why nginx proxies `/api`

The bundle and the API are served from the **same origin**. This is a design decision,
not a convenience:

* the httpOnly session cookie is first-party, so it works without `SameSite=None`
  (which would force HTTPS, including locally);
* `flask-cors` never has to answer a preflight, and `CLIENT_ORIGIN` stops being a
  thing that can be misconfigured;
* the client's `const BASE = "/api"` is correct in dev and in production alike.

The live notification stream (`/api/notifications/stream`) gets its own nginx
location with `proxy_buffering off` — with buffering on, nginx would hold each SSE
event until its buffer filled and the UI would update in bursts.

---

## Environment variables

**None are required locally.** Copy the template only when you want to change something:

```bash
cp .env.example .env
```

`.env` is gitignored. Compose reads it automatically.

### What you may want to set

| Variable | Default | Why you'd change it |
|---|---|---|
| `WEB_PUBLISH_PORT` | `8080` | Something else already owns 8080. |
| `API_PUBLISH_PORT` | `5002` | Loopback port the API is published on. |
| `DB_PUBLISH_PORT` | `3307` | Loopback port MySQL is published on. The tests and a non-Docker server expect 3307. |
| `DB_NAME`, `DB_USER` | `lolsuit`, `lolsuit` | The application database and account the `db` container creates on first boot. |
| `DB_PASSWORD` | `lolsuit-dev` | **Mandatory** anywhere that is not your laptop. |
| `MYSQL_ROOT_PASSWORD` | `lolsuit-root-dev` | Same. Only the local `db` container uses it; the app never connects as root. |
| `PHASE_MINUTES` | `1440` | A trial phase is a day. Set `2` to watch a case reach a verdict over a coffee. |
| `TICK_SECONDS` | `15` | The worker's tick period (passed to `worker` only). |
| `FLASK_SESSION_SECURE` | `0` | Set `1` behind HTTPS. It **breaks plain-HTTP local dev**, so it stays 0 here. |
| `CLIENT_ORIGIN` | `http://localhost:8080` | Only consulted when something calls the API directly instead of through nginx. |
| `MAIL_BACKEND` | `console` | `smtp` to actually send the password-reset email. On `console` the link is printed to `docker compose logs server`. |
| `MAIL_FROM`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_USE_TLS` | `court@lolsuit.local`, empty, `587`, empty, empty, `1` | Only read when `MAIL_BACKEND=smtp`. See the commented Brevo block in `.env.example`. (Outside compose the code defaults differ: `SMTP_HOST=localhost`, `SMTP_PORT=25`, TLS off.) |
| `RESET_COOLDOWN_SECONDS` | `60` | How long before a second reset link is sent to the same account. |

Not every variable the code reads is forwarded by `docker-compose.yml`. In particular
`RESET_TTL_MINUTES`, `UPLOAD_MAX_BYTES`, `SESSION_TTL_DAYS`, the `SSE_*` knobs and the
worker's `SWEEP_EVERY_TICKS` / `HOUSEKEEPING_EVERY_TICKS` / `BOT_COOLDOWN_MINUTES`
reach no container, so setting them in `.env` has no effect under Docker — they take
their code defaults. `UPLOAD_DIR` is pinned to `/app/uploads`. The per-variable table in
[docs/configuration.md](docs/configuration.md) says which are forwarded.

### The bots' brain (all optional)

Compose's default is `BRAIN_FORCE_OFFLINE=1` (the code's own default is off): a
deterministic offline generator, fully functional, no credentials, no network. To use a
real model set `BRAIN_FORCE_OFFLINE=0` and either configure a credential chain with
`LLM_CREDENTIALS` (plus `GEMINI_KEY_1`…`GEMINI_KEY_3`, which compose forwards for
`key_env=` to name — see [docs/brain.md](docs/brain.md)), or pick one legacy single
provider:

* `LLM_PROVIDER=bedrock` with `AWS_REGION` — credentials come from the standard AWS
  chain (an instance role in production, never pasted keys);
* `LLM_PROVIDER=anthropic` with `LLM_API_KEY` — the direct API;
* `LLM_PROVIDER=gemini` with `LLM_API_KEY` — one key, no region. Its free tier is per
  model and per Google Cloud *project* (not per key): ~1,000 requests a day on the
  default `gemini-2.5-flash-lite`, and an unpublished allowance in the tens on the
  newest Flash models. Watch the spend against `SOCIAL_EVERY_TICKS` on the admin
  dashboard's AI tab.

`LLM_MODEL` is optional; empty means the provider's own default. There is a fourth
provider, `gateway`, for a box with no AWS identity — it needs `LLM_API_KEY` and
`LLM_ENDPOINT`, both of which compose forwards to `server` and `worker`; see
`prod/.env.example` for an example. Note that compose passes `LLM_PROVIDER` through as
an **empty string** when unset, so with `BRAIN_FORCE_OFFLINE=0` and no
`LLM_CREDENTIALS` you must set `LLM_PROVIDER` explicitly.

### Secrets

Configuration reaches a container through the **environment**, never through a
Dockerfile. A value baked into an image layer is readable by anyone who can pull the
image. Both `.dockerignore` files exclude `.env` for the same reason.

---

## Demo accounts

The `seed` service creates them. All share the password **`demo1234`**.

| Email | Role |
|---|---|
| `admin@lolsuit.local` | Admin — sees the moderation queue |
| `dana@lolsuit.local` | Regular user (files the demo case) |
| `yoni@lolsuit.local` | Regular user |
| `maya@lolsuit.local` | Regular user |

Plus 31 bot accounts under `@bots.lolsuit.local` — 20 jurors, 8 judges, 3 moderators.

Seeding is **idempotent**: keyed on email (and on the case's title), so it runs on
every `up` without ever duplicating a row, and re-running only refreshes descriptive
columns. It never resets a password that has since been changed.

---

## Everyday commands

Most of these also have a `make` shortcut (`make up`, `make logs S=server`, `make
seed`, `make db-shell`, …) — `make help` lists them, and
[docs/development.md](docs/development.md) has the full table.

```bash
docker compose up --build          # build and start everything, logs in the foreground
```

```bash
docker compose up -d --build       # same, detached
```

```bash
docker compose ps                  # what is running, and whether it is healthy
```

```bash
docker compose logs -f server      # follow one service (or omit the name for all)
```

```bash
docker compose down                # stop, keep the database
```

```bash
docker compose down -v             # stop and WIPE both volumes
```

`-v` removes `uploads` as well as `db-data` — every avatar and every piece of
evidence on your local site goes with the database.

### Resetting the database

`/docker-entrypoint-initdb.d` runs **only on an empty data volume**. After editing
`database/init.sql`, a plain restart will not pick it up:

```bash
docker compose down -v && docker compose up --build
```

A wipe is the blunt answer, and it costs you every account and case you have
locally. Every one of the 24 `CREATE TABLE` statements in `init.sql` is
`IF NOT EXISTS`, so when the change is a **new table** you can apply just that one
against the running database instead — this is what to do for `agent_events` and
`agent_memories`, which are what the bots remember about the people they talk to.
(They supersede the older `bot_memories`: `init.sql` still creates it, the
application no longer reads it — "forget me" still deletes from it.)

```bash
docker compose exec -T db mysql --default-character-set=utf8mb4 -ulolsuit -plolsuit-dev lolsuit < database/init.sql
```

(Substitute your own `DB_PASSWORD` if you changed it.) That adds anything missing and
touches nothing that already exists. It is not a migration tool: it cannot add a column
to a table that is already there — for those, apply the matching file from
[`prod/migrations/`](prod/migrations/) (e.g. `004-brain-credentials.sql` adds columns to
`brain_calls`) or wipe.

The same applies to `case_follows` and `case_activity`, the two tables behind
"My Feed": a fresh `docker compose down -v && docker compose up --build` picks
them up from `init.sql`, and an existing local database gets them from the
command above. A **production** database needs `prod/migrations/002-my-feed.sql`
instead, which also backfills the follows and activity timestamps for cases that
already exist.

### Running more than one worker

Safe by construction — the loop takes a MySQL advisory lock and every unit of work
is claimed with `FOR UPDATE SKIP LOCKED`:

```bash
docker compose up -d --scale worker=3
```

---

## Verifying it works

```bash
curl -s http://localhost:8080/api/health | python3 -m json.tool
```

A healthy stack answers `200` with `"database": "up"` and a `worker` block whose
`seconds_since_tick` keeps resetting:

```json
{
    "brain": {
        "configured": "offline",
        "last_backend": "unknown",
        "last_error": null,
        "llm_calls": 0,
        "llm_failures": 0,
        "cache_reads": 0,
        "cache_writes": 0,
        "missing_capability": null
    },
    "database": "up",
    "phase_minutes": 1440,
    "server_time": "2026-09-06T15:32:44",
    "status": "ok",
    "worker": {
        "tick_count": 2418,
        "last_tick_at": "2026-09-06T15:32:37",
        "seconds_since_tick": 7.6,
        "last_error": null
    }
}
```

`brain` reports intent and outcome separately, and that is the point of it:
`configured` is what the settings say will be tried, `last_backend` is what actually
answered last. They disagreeing is how a broken model backend looks — the court
quietly falls back to the offline generator and nothing else goes wrong.

The endpoint answers **503** while MySQL is unreachable, which is exactly what the
container healthcheck keys on.

### Expected noise in the logs

`mysql:8.0` emits several warnings of its own at first boot — a deprecated
`--skip-host-cache`, a self-signed `ca.pem`, and `Unable to load ... zone.tab` while
it loads timezone tables. They come from the stock image, not from this project, and
are safe to ignore. LolSuit's own four services should log nothing above INFO.

---

## The images

| Image | Size | Notes |
|---|---|---|
| `lolsuit/server` | ~340 MB | `python:3.12-slim`. Dependencies built into a venv in a `deps` stage; pip and its cache stay behind. |
| `lolsuit/web` | ~75 MB | `node:22-alpine` builds the bundle, `nginx:1.27-alpine` serves it. No Node, no `node_modules`, no source in the final image. |

**Nothing runs as root.** `server`/`worker`/`seed` run as `lolsuit` (uid 1001); `web`
runs as `nginx` (uid 101) and therefore listens on 8080 rather than 80 — ports below
1024 would need `CAP_NET_BIND_SERVICE`, and the point of dropping privileges is not
to need capabilities.

**Layer caching** is what the `COPY` ordering is for. `requirements.txt` /
`package.json` + `package-lock.json` are copied and installed *before* any source, so
editing a service module or a component re-runs the build but not the install.

---

## Local development without Docker

Still supported, and the ports now agree with the containers:

```bash
docker compose up -d db            # just MySQL, on 127.0.0.1:3307
```

```bash
cp .env.example .env               # first time only — required, see below
cd server && python -m app.seed && python run.py
```

The API listens on `5002`; `client/vite.config.ts` proxies `/api` there. Copying
`.env.example` to `.env` (required — the code's own DB defaults do not match the
container), creating the virtualenv and installing the requirements first are in
[README.md](README.md#running-locally-without-docker). On Windows, use the `py` launcher
where these docs say `python`.

```bash
cd client && npm run dev           # http://localhost:5174
```
