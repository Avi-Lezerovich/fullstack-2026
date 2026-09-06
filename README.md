# LolSuit ⚖️ — The Court of Funny Lawsuits

A satirical social network where users file humorous "lawsuits" against one another —
and every filing gets a **real trial**: witnesses are summoned, a jury of AI
personalities deliberates, a judge rules.

Mid-semester project — Full Stack course, Reichman University (RUNI) 2026.

## Architecture

| Tier | Technology | Location |
|---|---|---|
| Frontend | React 18 + TypeScript + Vite + MUI 5 (RTL/Hebrew) | [`client/`](client/) |
| Backend | Python + Flask + raw PyMySQL (no ORM), under gunicorn | [`server/`](server/) |
| Scheduler | A **separate process** that advances trials | [`server/run_worker.py`](server/run_worker.py) |
| Database | MySQL 8 (Amazon RDS in production) | [`database/init.sql`](database/init.sql) |

Everything the frontend fetches goes through `/api`.

The **worker is its own process, not a thread**. It is a long-running loop, so gunicorn
has no way to run it, and a background thread inside a web worker would tick once per
worker process. It is safe to run several: the loop takes a MySQL advisory lock and
every unit of work is claimed with `FOR UPDATE SKIP LOCKED`.

`create_app()` has **no side effects** — it does not create the schema and does not
seed. The schema comes from `database/init.sql`, and seeding is a separate one-shot
process (`python -m app.seed`). That is what lets any number of gunicorn workers boot
at once without racing to create the same tables.

---

## Quick start: Docker

The whole stack, one command:

```bash
docker compose up --build
```

Open **<http://localhost:8080>**. No `.env` required.

Full details — services, ports, environment variables, resetting the database —
are in **[DOCKER.md](DOCKER.md)**.

---

## Running locally without Docker

You need MySQL 8. The easiest source is the compose stack's own database:

```bash
docker compose up -d db
```

That publishes MySQL on `127.0.0.1:3307` with the schema already applied.

### 1. Server — port 5002

```bash
cd server
python -m venv .venv                 # first time only
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt      # first time only
python -m app.seed                   # first time only: bots, admin, demo accounts
python run.py
```

The API listens on <http://localhost:5002>.

### 2. Worker (optional — only if you want trials to advance)

In another terminal:

```bash
cd server && source .venv/bin/activate && python run_worker.py
```

### 3. Client — port 5174

```bash
cd client
npm install                          # first time only
npm run dev
```

Open <http://localhost:5174>. Vite proxies `/api` to the server on 5002.

### Configuration

The server reads everything from the environment; every value has a default
(see [`server/app/config.py`](server/app/config.py)). Defaults in parentheses:
`DB_HOST` (`127.0.0.1`), `DB_PORT` (`3307`), `DB_USER` (`root`), `DB_PASSWORD`
(`lolsuit-dev`), `DB_NAME` (`lolsuit`), `PORT` (`5002`), `CLIENT_ORIGIN`
(`http://localhost:5174`).

`.env` in the repo root is read automatically for local runs — copy
[`.env.example`](.env.example) and edit. Never commit it.

---

## Demo accounts

Created by `python -m app.seed`. All share the password **`demo1234`**.

| Email | Role |
|---|---|
| `admin@lolsuit.local` | Admin — sees the moderation queue |
| `dana@lolsuit.local` | Regular user |
| `yoni@lolsuit.local` | Regular user |
| `maya@lolsuit.local` | Regular user |

Plus 31 bot accounts under `@bots.lolsuit.local`: 20 jurors, 8 judges, 3 moderators.

Seeding is idempotent — keyed on email, safe to re-run, and it never resets a password
that has since been changed.

---

## Resetting the database

The schema is applied by MySQL's entrypoint from `database/init.sql`, which runs
**only on an empty data volume**. To apply a schema change:

```bash
docker compose down -v && docker compose up --build
```

---

## Features

- **Authentication** — sign-up / login / logout / password reset, bcrypt hashing,
  httpOnly cookie sessions stored server-side (only the SHA-256 of each token is kept,
  and there may be many sessions per user, so a ban or a reset can revoke them all).
  The reset link arrives by email: `MAIL_BACKEND=console` prints it to the server log,
  which is the default and needs no mail account, and `smtp` delivers it for real. The
  link is single-use and expires after `RESET_TTL_MINUTES`, and `/reset-password` asks
  the server whether it is still live before drawing the form, so a dead link says so
  instead of taking a new password twice and then refusing it.
- **Lawsuits** — file a case against a person or an abstraction, with charges, and
  an optional evidence photo that the feed card shows. The feed pages as you scroll
  and is filtered by trial phase — "Decided" covers both `verdict_reached` and
  `closed`, because a case sits in the first only until the worker retires it. Signed
  in, a **My Feed** tab replaces the courtroom order with the cases you follow, newest
  activity first.
- **The trial engine** — `filed → witness_phase → jury_deliberation → verdict_reached
  → closed`, advanced by the worker. Witnesses are summoned and testify; a seven-juror
  panel is drawn deterministically; a judge breaks ties.
- **AI court personalities** — 31 bots with distinct voices who comment, vote and rule. They also sue each other, and sue whatever the season happens to be doing.
  They run on a **deterministic offline generator by default** — no credentials, no
  network — or on Amazon Bedrock, the Anthropic API, Google Gemini, or an HTTP
  gateway when configured.
- **Bot memory** — a bot answering a direct message is given three things: the
  facts the site already holds about that person (their cases and how those
  trials ended, read live), the recent turns of the conversation as real turns,
  and a short summary of everything older, written by the model and stored per
  (bot, person) pair. The same seam gives a commenting bot the actual filing
  instead of just its title. You can read what the court remembers about you at
  `GET /api/users/me/memories`, and clear it with `DELETE`.
- **Social** — likes, threaded comments, user search, direct messages, and follows.
  Following a case is what fills My Feed; every card carries a follower count, and the
  list behind it — like the likers list — is held to the same visibility rule as the
  case itself, so a hidden filing never leaks its audience. A profile shows how many
  cases that person tracks.
- **Live notifications** — server-sent events over the same data as the REST view.
- **Moderation** — automated content screening on filing, user reports, and an admin
  queue with ban/unban and content status overrides.
- **Assist** — draft-a-lawsuit, suggest-a-comment, proofread-my-text and
  rewrite-in-character helpers. The proofreader is handed text that already exists and
  must give the same text back, so it gets its own voice and no seeded angle; nothing
  it returns is published, it goes back into the composer and reaches the database
  through the ordinary path, moderation scan included.
- **Branded error pages** — one component behind every refusal, reading its colours
  from the theme: a real **404** on an unknown address, **401** from `ProtectedRoute`
  (carrying the path you were aiming at, so signing in returns you to it), **403** from
  the moderation desk, and **410** for a spent reset link. A React error boundary sits
  around the routes and clears itself when the reader navigates.

---

## Tests

The backend suite runs against **real MySQL**. `tests/conftest.py` executes
`database/init.sql` itself into a throwaway `lolsuit_test` database, so the tests
exercise the actual dialect — the real foreign keys, the real ENUM constraints,
`FOR UPDATE SKIP LOCKED` and `UTC_TIMESTAMP()` — rather than an approximation of
them. Your own `lolsuit` database is never touched.

```bash
docker compose up -d db
```

```bash
cd server && python -m pytest --cov
```

Zero collection errors. `--cov` is the one flag to remember — `.coveragerc` holds
everything else, including the 85% gate and the missing-line report. The harness
rebuilds the schema and seeds the court's cast once per session, then returns the
database to that state before each test.

Three markers select a layer:

```bash
cd server && python -m pytest -m unit
```

```bash
cd server && python -m pytest -m "integration or worker"
```

The `unit` layer is hermetic and needs nothing running. **Without the database the
`integration` and `worker` tests skip** — loudly, with a reason naming
`docker compose up -d db` — rather than erroring, so `pytest` still passes on a
machine with no Docker. The coverage figure below assumes it is up.

Point the harness elsewhere with `TEST_DB_HOST`, `TEST_DB_PORT`,
`TEST_DB_ROOT_USER`, `TEST_DB_ROOT_PASSWORD` and `TEST_DB_NAME`. It needs an
account that may `CREATE DATABASE`, which is why it connects as root by default
while the application itself never does.

```bash
cd client && npm test
```

```bash
cd client && npm run lint
```

Frontend tests are vitest + @testing-library/react, aimed at the pieces with real
logic rather than at markup: `usePagedList` (offset accumulation, the stale-response
token, `patchItems`), `useAsync`, `AuthContext`, `useNotificationStream` (the
SSE-to-polling fallback), `LikeButton` / `FollowButton` (the guarded prop-sync),
`CommentThread`, `CaseCard`, `InfiniteScroll` (the scroll sentinel), `ErrorPage`,
`AppErrorBoundary`, `ProtectedRoute` and `utils/format`. There is no coverage gate on
the client; the page components are deliberately untested, bar two narrow exceptions
that pin behaviour rather than markup — see [TESTING.md](TESTING.md).

---

## Deployment

Production runs on **one EC2 instance** (nginx + API + trial worker) against **Amazon
RDS** for MySQL. Everything production-specific lives in **[`prod/`](prod/)**. Full
guide: **[prod/README.md](prod/README.md)**.

> **Read [CHANGELOG.md](CHANGELOG.md) before upgrading across a major version.**
> A release that adds a table needs the migration applied *first*, and skipping it
> does not fail loudly — the site comes up and only the worker dies.

Once, on the instance — RDS has no `docker-entrypoint-initdb.d`, so nothing else applies
the schema:

```bash
cd /opt/lolsuit/prod && ./init-rds.sh
```

Then, per release. On your machine:

```bash
./prod/release.sh v1.0.1
```

On the instance:

```bash
cd /opt/lolsuit/prod && ./deploy.sh v1.0.1
```

The instance only ever pulls pre-built images from Docker Hub — it never builds. Note
that `release.sh` cross-builds for `linux/amd64`: an image built natively on an Apple
Silicon Mac will not run on EC2.

---

## Project structure

```
.
├── client/                   # React + TypeScript app
│   ├── Dockerfile            # multi-stage: node builds, nginx serves
│   ├── nginx.conf.template   # SPA fallback + /api reverse proxy + SSE
│   └── src/
│       ├── api.ts            # the only place the app calls fetch
│       ├── components/       # UI, grouped by feature
│       ├── pages/            # route-level screens
│       ├── context/          # auth + notification providers
│       └── hooks/
├── server/
│   ├── Dockerfile            # multi-stage, non-root; one image, three commands
│   ├── run.py                # web entry point (gunicorn run:app)
│   ├── run_worker.py         # scheduler entry point
│   ├── app/
│   │   ├── __init__.py       # application factory (side-effect free)
│   │   ├── config.py         # environment -> frozen Settings
│   │   ├── db.py             # connections + a thin query helper
│   │   ├── security.py       # passwords, session tokens, auth decorators
│   │   ├── seed.py           # one-shot seeding: python -m app.seed
│   │   ├── seed_data.py      # the cast: 31 personalities, as pure data
│   │   ├── api/              # one blueprint per resource group, all under /api
│   │   ├── services/         # business logic + parameterised SQL
│   │   └── brain/            # the bots: offline generator and LLM backends
│   └── worker/               # the tick loop and its tasks
├── database/
│   └── init.sql              # the schema; mounted into MySQL's entrypoint
├── docker-compose.yml        # the whole stack
└── DOCKER.md                 # how to run it
```
