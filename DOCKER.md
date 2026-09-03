# Running LolSuit with Docker

Everything — frontend, API, trial scheduler and MySQL — comes up with one command.

```bash
docker compose up --build
```

Then open **<http://localhost:8080>**.

No `.env` is required. Every variable has a working local default; see
[Environment variables](#environment-variables) for what to set and when.

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
| `DB_PASSWORD` | `lolsuit-dev` | **Mandatory** anywhere that is not your laptop. |
| `MYSQL_ROOT_PASSWORD` | `lolsuit-root-dev` | Same. Only the local `db` container uses it; the app never connects as root. |
| `PHASE_MINUTES` | `1440` | A trial phase is a day. Set `2` to watch a case reach a verdict over a coffee. |
| `TICK_SECONDS` | `15` | How often the worker wakes up. |
| `FLASK_SESSION_SECURE` | `0` | Set `1` behind HTTPS. It **breaks plain-HTTP local dev**, so it stays 0 here. |
| `CLIENT_ORIGIN` | `http://localhost:8080` | Only consulted when something calls the API directly instead of through nginx. |
| `MAIL_BACKEND` | `console` | `smtp` to actually send the password-reset email. On `console` the link is printed to `docker compose logs server`. |
| `MAIL_FROM`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_USE_TLS` | — | Only read when `MAIL_BACKEND=smtp`. See the commented Brevo block in `.env.example`. |
| `RESET_COOLDOWN_SECONDS` | `60` | How long before a second reset link is sent to the same account. |

### The bots' brain (all optional)

The default is `BRAIN_FORCE_OFFLINE=1`: a deterministic offline generator, fully
functional, no credentials, no network. To use a real model set
`BRAIN_FORCE_OFFLINE=0` and pick `LLM_PROVIDER=bedrock` (credentials come from the
standard AWS chain — an instance role in production, never pasted keys) or
`LLM_PROVIDER=anthropic` with `LLM_API_KEY`.

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
docker compose down -v             # stop and WIPE the database volume
```

### Resetting the database

`/docker-entrypoint-initdb.d` runs **only on an empty data volume**. After editing
`database/init.sql`, a plain restart will not pick it up:

```bash
docker compose down -v && docker compose up --build
```

A wipe is the blunt answer, and it costs you every account and case you have
locally. Every `CREATE TABLE` in `init.sql` is `IF NOT EXISTS`, so when the
change is a **new table** you can apply just that one against the running
database instead — this is what to do for `bot_memories`, which is what the
bots remember about the people they talk to:

```bash
docker compose exec -T db mysql -ulolsuit -plolsuit-dev lolsuit < database/init.sql
```

That adds anything missing and touches nothing that already exists. It is not a
migration tool: it cannot add a column to a table that is already there.

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
    "brain": "offline",
    "database": "up",
    "phase_minutes": 1440,
    "status": "ok",
    "worker": { "tick_count": 2, "seconds_since_tick": 12.6, "last_error": null }
}
```

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
| `lolsuit/server` | ~256 MB | `python:3.12-slim`. Dependencies built into a venv in a `deps` stage; pip and its cache stay behind. |
| `lolsuit/web` | ~78 MB | `node:22-alpine` builds the bundle, `nginx:1.27-alpine` serves it. No Node, no `node_modules`, no source in the final image. |

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
cd server && .venv/bin/python -m app.seed && .venv/bin/python run.py
```

The API listens on `5002`; `client/vite.config.ts` proxies `/api` there.

```bash
cd client && npm run dev           # http://localhost:5174
```
