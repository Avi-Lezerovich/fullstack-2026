# Configuration reference

Every environment variable in the project, and where it takes effect. The sources:
[`server/app/config.py`](../server/app/config.py), which every Python process reads;
[`docker-compose.yml`](../docker-compose.yml) (local);
[`prod/docker-compose.yml`](../prod/docker-compose.yml) (EC2); and the two templates,
[`.env.example`](../.env.example) and [`prod/.env.example`](../prod/.env.example).

How values arrive:

- **Outside Docker**, `config.py` calls `load_dotenv` on the repo-root `.env`, which never
  overrides a variable that is already set. Anything missing takes the **code default**.
  `get_settings()` re-reads the environment on every call.
- **Under Docker Compose**, compose reads `.env` for `${VAR}` substitution. A container
  only sees a variable that its service's `environment:` block lists. Anything not listed
  takes the code default inside the container, **whatever `.env` says**.

Column key: **Code** is the default in `config.py`. **Local** is what local compose
passes: a value means it is forwarded with that default, and "—" means it is not
forwarded at all. **Prod** is the same for `prod/docker-compose.yml`, where `required`
means `${VAR:?}` (the deploy aborts if it is unset).

## Database and server

| Variable | Code | Local | Prod | Notes |
|---|---|---|---|---|
| `DB_HOST` | `127.0.0.1` | `db` (fixed) | required | RDS endpoint in prod, with no scheme and no port |
| `DB_PORT` | `3307` | `3306` (fixed) | `3306` | 3307 is the loopback port the local `db` publishes |
| `DB_USER` | `root` | `lolsuit` | required | **The code default does not work against the compose DB.** Its root password is `lolsuit-root-dev`, so a non-Docker run needs `.env` (which sets `lolsuit`) |
| `DB_PASSWORD` | `lolsuit-dev` | `lolsuit-dev` | required | |
| `DB_NAME` | `lolsuit` | `lolsuit` | required | |
| `PORT` | `5002` | `5002` (fixed) | `5002` (fixed) | gunicorn's bind port inside the container |
| `CLIENT_ORIGIN` | `http://localhost:5174` | `http://localhost:8080` | required | CORS origin. Only matters when something calls the API cross-origin, since nginx and the Vite proxy are same-origin |
| `FLASK_SESSION_SECURE` | off | `0` | `1` | `1` sets `Secure; SameSite=None` on the cookie. `prod/.env.example` ships `0` for plain HTTP; flip it to `1` behind TLS |
| `SESSION_TTL_DAYS` | `7` | — | — | Not in any template |
| `BCRYPT_ROUNDS` | `12` (min 4) | — | — | Only the test suite lowers it, to `4` |
| `GUNICORN_WORKERS`, `GUNICORN_THREADS` | — | image default `2`, `16` | `2`, `16` | Read by the image's `CMD` ([`server/Dockerfile`](../server/Dockerfile)), not by `config.py` |

## Auth and mail

| Variable | Code | Local | Prod | Notes |
|---|---|---|---|---|
| `RESET_TTL_MINUTES` | `30` | — | — | Listed in `.env.example`, but neither compose file forwards it |
| `RESET_COOLDOWN_SECONDS` | `60` | `60` | `60` | Minimum gap between two reset emails to one account |
| `MAIL_BACKEND` | `console` | `console` | `console` | `smtp` actually sends. `console` prints the link to the server log |
| `MAIL_FROM` | `court@lolsuit.local` | same | same | |
| `SMTP_HOST` | `localhost` | empty | empty | |
| `SMTP_PORT` | `25` | `587` | `587` | AWS throttles outbound 25 on EC2 |
| `SMTP_USER`, `SMTP_PASSWORD` | empty | empty | empty | |
| `SMTP_USE_TLS` | off | `1` | `1` | |

Mail variables are passed to `server` only, because the worker sends no mail.

## Uploads and SSE

| Variable | Code | Local | Prod | Notes |
|---|---|---|---|---|
| `UPLOAD_DIR` | `server/uploads` | `/app/uploads` (fixed, volume) | `/app/uploads` (fixed) | |
| `UPLOAD_MAX_BYTES` | `5242880` (5 MiB) | — | — | nginx separately caps the body at `6m` ([`client/nginx.conf.template`](../client/nginx.conf.template)) |
| `SSE_POLL_SECONDS` | `2.0` | — | — | How often the stream polls `notifications` |
| `SSE_MAX_SECONDS` | `300` | — | — | Stream lifetime before the client reconnects |
| `SSE_MAX_STREAMS` | `50` | — | — | Per process. Over the cap the endpoint returns 503 |

## Worker

| Variable | Code | Local | Prod | Notes |
|---|---|---|---|---|
| `PHASE_MINUTES` | `1440` | `1440` | `1440` | Length of one trial "day". Set `2` to watch a trial finish. Forwarded to both `server` and `worker` |
| `TICK_SECONDS` | `15` | `15` (worker only) | `15` | The tick period, read once at worker start |
| `SOCIAL_EVERY_TICKS` | `20` | passes `""`, so code default | same | A spend dial: each social pass makes model calls |
| `SWEEP_EVERY_TICKS` | `4` | — | — | Interval for the moderation sweep and the arbiter |
| `HOUSEKEEPING_EVERY_TICKS` | `240` | — | — | Interval for purging stale auth rows |
| `BOT_COOLDOWN_MINUTES` | `30` | — | — | Minimum gap between one bot's social actions |
| `JURY_SEED_SALT` | `lolsuit-v2` | — | — | Seeds the jury draw and the weighted rolls |
| `REPEAT_OFFENDER_THRESHOLD` | `3` | — | — | Number of prior hides at which the arbiter bans |

See [worker.md](worker.md#9-configuration).

## Brain / LLM

| Variable | Code | Local | Prod | Notes |
|---|---|---|---|---|
| `BRAIN_FORCE_OFFLINE` | off | `1` | `1` | **The code and compose defaults differ.** Compose runs offline unless you set `0` |
| `LLM_CREDENTIALS` | empty | forwarded | forwarded | The credential chain, as `;`-separated records. See [brain.md](brain.md#the-credential-chain--chainpy) |
| `GEMINI_KEY_1`, `GEMINI_KEY_2`, `GEMINI_KEY_3` | — | forwarded | forwarded | Read only when a record's `key_env=` names them. Any variable name works outside compose |
| `LLM_PROVIDER` | `bedrock` | passes `""` | passes `""` | Legacy single credential. Used only when `LLM_CREDENTIALS` has no valid record. Under compose an unset value becomes empty, so you must set it explicitly |
| `LLM_API_KEY` | empty | forwarded | forwarded | For `anthropic`, `gemini` and `gateway`. Bedrock ignores it |
| `LLM_ENDPOINT` | empty | forwarded | forwarded | Needed by `gateway` only |
| `LLM_MODEL` | empty (provider default) | forwarded | forwarded | |
| `LLM_TIMEOUT_SECONDS` | `60` | passes `""`, so `60` | same | |
| `AWS_REGION` / `AWS_DEFAULT_REGION` | empty | `AWS_REGION` only | `AWS_REGION` only | Setting it is what makes `bedrock` usable |
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`, `AWS_BEARER_TOKEN_BEDROCK` | — | — | forwarded | Read by boto3, not by `config.py`. An instance role is preferred over keys |
| `BRAIN_CACHE_TTL` | `5m` | — | — | Only `1h` is accepted as an alternative |
| `TOPICAL_SUBJECTS` | empty | forwarded | forwarded | Comma-separated, operator-chosen "current" subjects |

Brain variables are forwarded to both `server` and `worker`. The full credential-chain
semantics (caps, RPM, cooldowns) are in [brain.md](brain.md).

## Compose, ports and images (not read by Python)

| Variable | Default | Used by |
|---|---|---|
| `WEB_PUBLISH_PORT` | `8080` local, `80` prod | the `web` port mapping |
| `WEB_PUBLISH_BIND` | `0.0.0.0` (prod only) | prod `web`. Set `127.0.0.1` behind Caddy |
| `API_PUBLISH_PORT` | `5002` | local loopback port for the API |
| `DB_PUBLISH_PORT` | `3307` | local loopback port for MySQL |
| `MYSQL_ROOT_PASSWORD` | `lolsuit-root-dev` | local `db` only. The tests' `TEST_DB_ROOT_PASSWORD` defaults to the same value |
| `API_UPSTREAM` | `server:5002` | nginx upstream, substituted by [`client/docker-entrypoint.sh`](../client/docker-entrypoint.sh) |
| `TAG`, `DOCKERHUB_USERNAME` | required (prod) | which images prod pulls. `deploy.sh` rewrites `TAG` |
| `SERVER_MEMORY_LIMIT`, `WORKER_MEMORY_LIMIT`, `WEB_MEMORY_LIMIT` | `512m`, `512m`, `128m` | prod memory limits |

## Scripts and tests

| Variable | Default | Used by |
|---|---|---|
| `TEST_DB_HOST`, `TEST_DB_PORT`, `TEST_DB_ROOT_USER`, `TEST_DB_ROOT_PASSWORD`, `TEST_DB_NAME` | `127.0.0.1`, `3307`, `root`, `lolsuit-root-dev`, `lolsuit_test` | [`server/tests/conftest.py`](../server/tests/conftest.py) |
| `PLATFORMS` | `linux/amd64` | [`prod/release.sh`](../prod/release.sh). The script also reads `APP_NAME`, `BUILDER` and `REGISTRY`; see its header |
| `HEALTH_TIMEOUT`, `COMPOSE_FILE` | `120`, `docker-compose.yml` | [`prod/deploy.sh`](../prod/deploy.sh) |
| `SCHEMA_FILE`, `MYSQL_IMAGE` | see the script | [`prod/init-rds.sh`](../prod/init-rds.sh) |

`APP_VERSION` is set as an `ENV` in the server image, but nothing reads it (see
[known-issues.md](known-issues.md)).
