# Containers and deployment

How the application is packaged and how the pieces fit together — two images, five
services, one public port, and the same images running locally and in production.

> **This is the architecture view.** The step-by-step runbooks already exist and are not
> repeated here:
> - [DOCKER.md](../DOCKER.md) — running the local stack: commands, every environment
>   variable, demo accounts, resetting the database, expected log noise.
> - [prod/README.md](../prod/README.md) — deploying to EC2 + RDS: security groups,
>   instance preparation, releases, rollback, HTTPS, backups.

---

## 1. Two images, five services

| Service | Image | Command | Port | Role |
|---|---|---|---|---|
| `db` | `mysql:8.0` | — | `127.0.0.1:3307` | **Local only.** Schema applied from `database/init.sql` on first boot. |
| `seed` | `lolsuit/server` | `python -m app.seed` | — | One-shot, exits 0. The 31 bots, the admin, the demo accounts. |
| `server` | `lolsuit/server` | `gunicorn … run:app` | `127.0.0.1:5002` | The Flask API. See [api.md](api.md). |
| `worker` | `lolsuit/server` | `python run_worker.py` | — | The trial scheduler. See [worker.md](worker.md). |
| `web` | `lolsuit/web` | nginx | **`8080`** | The built bundle, plus the `/api` reverse proxy. |

**`server`, `worker` and `seed` are three commands over one image.** They share every
dependency, so building three would only mean three caches to invalidate. Compose
overrides the command per service; the image's own `CMD` is the gunicorn one.

## 2. The server image

[`server/Dockerfile`](../server/Dockerfile). Build context is `server/`, not the repo
root — nothing in the running application reads `database/init.sql`, so the image has no
reason to carry the repo around.

- **Two stages.** Stage 1 builds a virtualenv at `/opt/venv`; stage 2 copies it wholesale.
  pip, its wheel cache and any transient build tooling stay behind. `requirements.txt` is
  copied alone, before any source, so the expensive layer is not invalidated by an edit to
  a service module.
- **Non-root**, a dedicated `lolsuit` system account with an explicit uid/gid 1001 so a
  bind-mounted file's ownership is predictable. The home directory is not optional despite
  nobody logging in: gunicorn's control server puts its socket under `$HOME`.
- **`/app/uploads` is created and chowned in the image**, before the volume is mounted
  over it. Docker seeds a fresh named volume from the image's directory including
  ownership — but if the mount point does not exist it creates one owned by root, and the
  non-root app then cannot write a single file. Silent until the first upload.
- **Provenance labels are the last thing in the file.** `ARG` invalidates every layer
  beneath it, so declared at the top a version bump would re-run `pip install`; down here
  it rebuilds a few bytes of metadata. `docker image inspect --format '{{json
  .Config.Labels}}'` then answers "which commit is actually running", which is the
  question you always have during an incident and can never get from a tag.
- **Healthcheck** hits `/api/health` with `urllib` (the slim base has no curl, and adding
  one for a healthcheck is not worth ~4 MB). That endpoint returns **503**, not 500, while
  MySQL is unreachable — exactly the semantics a healthcheck wants.
- **`CMD` runs gunicorn with `--worker-class gthread`**, not sync: an SSE stream holds its
  handler for minutes and sync workers would each be blocked by one subscriber. The
  `--timeout 600` is comfortably above `SSE_MAX_SECONDS` so a healthy stream is never
  killed mid-flight. It is wrapped in `sh -c … exec` so `${PORT}` expands *and* gunicorn
  still becomes PID 1 and receives SIGTERM directly — otherwise `docker stop` would wait
  out the full grace period on every deploy.

## 3. The web image

[`client/Dockerfile`](../client/Dockerfile) + [`client/nginx.conf.template`](../client/nginx.conf.template).

- **Node exists only to produce `dist/`.** The published image is nginx plus a few hundred
  kilobytes of static files — no Node, no `node_modules`, no source, and therefore nothing
  a CVE in a build-time dependency can reach. `npm ci` (not `install`) installs exactly the
  lockfile and fails loudly if it has drifted, and `npm run build` is `tsc -b && vite
  build`, so a type error fails the image build rather than shipping a broken bundle.
- **Unprivileged nginx**, which drives three details: it listens on **8080** rather than 80
  (ports below 1024 need `CAP_NET_BIND_SERVICE`, and the point of dropping privileges is
  not to need capabilities), the pid file and every temp path are relocated to `/tmp`, and
  the config is rendered by [`docker-entrypoint.sh`](../client/docker-entrypoint.sh)
  rather than by the stock image's envsubst step, which only runs as root.
- **`API_UPSTREAM` is substituted at container start**, defaulting to `server:5002`. That
  is what lets one image work against a compose service, an ALB or a host-network backend
  with no rebuild. The envsubst variable list is explicit, or it would also eat nginx's own
  `$host`, `$remote_addr` and `$uri`.

## 4. Why nginx fronts everything

The bundle and the API are served from the **same origin**, which is a design decision
rather than a convenience:

- the httpOnly session cookie is first-party, so it works without `SameSite=None` (which
  would force HTTPS, including locally);
- `flask-cors` never has to answer a preflight, and `CLIENT_ORIGIN` stops being a thing
  that can be misconfigured;
- the client's `const BASE = "/api"` is correct in dev and in production alike.

Four location blocks do something the generic proxy rule cannot:

| Location | Why it exists |
|---|---|
| `= /api/notifications/stream` | `proxy_buffering off` — with buffering on, nginx holds each SSE event until its buffer fills and the UI updates in bursts. Read/send timeouts of 3600s so nginx never severs a healthy stream. Placed **before** the generic rule. |
| `= /api/uploads` | `client_max_body_size 6m`. nginx's default is 1 MB, which would 413 every upload before it reached Flask. Raised here only, so the cap stays tight everywhere else. |
| `/assets/` | Vite fingerprints these filenames, so a year of immutable caching is safe; a new deploy simply requests different names. `= /index.html` is the opposite — never cached, or browsers keep asking for the previous deploy's asset names. |
| `/` | `try_files $uri $uri/ /index.html` — the app uses `BrowserRouter`, so `/users` and `/cases/3` are client-side routes with no file behind them. |

This is the third place the upload size is enforced, and deliberately so: nginx refuses an
oversized body, then Flask's `MAX_CONTENT_LENGTH` refuses it before the view runs, then
the view measures what actually arrived. The first two are defence; the third is the one
that produces a Hebrew error message. See [api.md](api.md#4-endpoints).

## 5. Start-up order

Compose enforces it with conditions, not with `sleep`:

```
db (healthy) ──> seed (exits 0) ──> server (healthy) ──> web
                              └───> worker
```

Two of those conditions are load-bearing:

- **`db` is not healthy until it answers over TCP.** The healthcheck pings
  `-h 127.0.0.1` rather than the unix socket, because during initialisation MySQL runs a
  temporary server that listens on the socket *only* — a socket ping would report healthy
  while `init.sql` was still being applied and let the API start against a half-built
  schema.
- **`web` waits for `server` to be healthy**, not merely started: nginx resolves its
  upstream's DNS name once at startup and would exit if `server` were not there yet.

`seed` runs to completion before anything serves traffic, so the API is never briefly up
against a database with no judges in it. It is idempotent (keyed on natural keys like a
user's email), so running it on every `up` is harmless — see [api.md](api.md#6-seeding).

The `worker` container has a healthcheck of its own, and it cannot be the image's HTTP
probe because the worker serves no HTTP. What "healthy" means for a scheduler is that it
is still ticking, and it already records every tick in `worker_state`, so the check is a
query rather than a new channel: fail if `last_tick_at` is more than 120 seconds old.

## 6. Only one port is public

`web` publishes `8080`. The API (`5002`) and MySQL (`3307`) are bound to `127.0.0.1` —
they exist for `curl`, Postman and the pytest suite, not for the browser, which reaches
the API through nginx.

## 7. State

| Volume | Holds | Notes |
|---|---|---|
| `db-data` | MySQL's data directory | Local only. `/docker-entrypoint-initdb.d` runs **only on an empty volume**, so editing `init.sql` needs `docker compose down -v`. |
| `uploads` | Avatars and evidence photos | Survives a rebuild, exactly like `db-data`. Without it every `up --build` would silently break every image on the site. |

In production `uploads` is **the only state not in RDS**. It is a named volume on the
instance's EBS root device, so it is not covered by RDS backups and does not survive
replacing the instance — back it up separately or move it to S3 (`prod/README.md`,
"Backups").

Everything else is in the database, which is what makes the worker and the web tier
restartable at any moment. See [database.md](database.md).

## 8. Local versus production

[`prod/docker-compose.yml`](../prod/docker-compose.yml) is a separate file, and the
differences are all deliberate:

| | Local (`docker-compose.yml`) | Production (`prod/docker-compose.yml`) |
|---|---|---|
| Database | a `db` container | **Amazon RDS.** No database container at all — backups, PITR and failover are somebody else's problem. `DB_HOST` is required with no default. |
| Images | `build:` from source | `image:` pulled from Docker Hub. The EC2 box has no source tree and no business compiling anything. |
| Secrets | `${VAR:-default}` | `${VAR:?message}` — a missing `DB_PASSWORD` aborts the deploy rather than silently booting production with `lolsuit-dev`. That single character is the most important difference in the file. |
| Version | `:local` | pinned to `${TAG}`. `latest` is a convenience for humans, not a thing to deploy — it makes "which version is running?" unanswerable and rollback impossible. |
| Logging | default | `json-file` with rotation on every service. Unbounded logs are the most common way a small instance fills its root volume and takes the site down. |
| Public port | `8080` | `80` on the host → `8080` in the container. TLS terminates in front of it (`WEB_PUBLISH_BIND=127.0.0.1`, then Caddy). |
| Cookies | `FLASK_SESSION_SECURE=0` | `1`, and `CLIENT_ORIGIN` is required. |

Because there is no `db` container to gate on, **`seed` becomes the first thing that
touches the database** in production, which makes it the de-facto connectivity check for
the whole deploy: a wrong security group shows up there, before `server` starts returning
500s to real users. It needs no retry wrapper — `app.seed` already calls `wait_for_db()`, which
defaults to 30 attempts two seconds apart and, with PyMySQL's 10s connect timeout, waits
roughly six minutes on its own. Wrapping that in a shell retry loop would multiply the
two.

## 9. Release and deploy

```
dev machine                          EC2 instance
───────────                          ────────────
prod/release.sh v1.0.1               prod/deploy.sh v1.0.1
  buildx --platform linux/amd64        1. pull the new images (old ones still serving)
  push  lolsuit-server:v1.0.1          2. recreate the containers — seconds
        lolsuit-web:v1.0.1             3. verify /api/health actually answers
        (+ :latest for humans)         4. if it does not, roll back, unprompted
```

Two details worth knowing before the first release:

- **`release.sh` never calls `docker build`.** This repo is developed on Apple Silicon and
  essentially every EC2 instance is x86_64; a plain build-and-push from a Mac publishes an
  arm64 image that pulls fine and then dies with `exec format error`. It uses `buildx`
  with an explicit `--platform` (default `linux/amd64`).
- **`deploy.sh` pulls before it recreates**, because pulling is the slow step and doing it
  first costs zero downtime. Step 4 is the reason it is a script rather than three lines
  in a runbook: a deploy that fails at 2am and leaves the site down until someone reads
  the runbook is worse than one that quietly puts the old version back.

The RDS schema is **not** applied by any compose file. `prod/init-rds.sh` runs once before
the first deploy, and `./init-rds.sh --check` verifies the tables are really there — worth
running after every schema change, because the script reads `init.sql` from the box's own
working copy, so an un-pulled repo silently applies the old schema and reports success.
See [database.md](database.md#migrations).

## 10. Configuration and secrets

Configuration reaches a container through the **environment, never through a Dockerfile**.
A value baked into an image layer is readable by anyone who can pull the image, and both
`.dockerignore` files exclude `.env` for the same reason.

Nothing is required locally — every variable has a working local default, and the default
brain is `BRAIN_FORCE_OFFLINE=1`, so `docker compose up` with an empty `.env` runs the
whole application end to end. The full tables live in [DOCKER.md](../DOCKER.md#environment-variables)
and `.env.example`; the subsystem docs cover their own knobs
([worker.md](worker.md#9-configuration), [brain.md](brain.md#9-configuration)).

## 11. Where each subsystem runs

| Container | Doc |
|---|---|
| `web` (nginx + bundle) | [client.md](client.md) |
| `server` (gunicorn) | [api.md](api.md) |
| `worker` | [worker.md](worker.md) — and [brain.md](brain.md), which it calls into |
| `db` / RDS | [database.md](database.md) |
| `seed` | [api.md](api.md#6-seeding) |

---

> **One stale comment worth knowing.** `client/Dockerfile` reuses the `nginx` account that
> `nginx:1.27-alpine` already defines and says it is uid 101; `client/nginx.conf.template`
> says nginx runs as uid 1001. Only one can be right — the Dockerfile's `USER nginx`
> resolves to whatever the base image defines — so the template's comment looks stale.
> Nothing depends on the number: what matters is that the user is unprivileged, which is
> why the pid file and temp paths live in `/tmp` and why the container listens on 8080.
