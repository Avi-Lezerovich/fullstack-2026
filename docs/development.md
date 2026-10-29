# Development workflow

How to work on LolSuit day to day. The first-run instructions are in
[README.md](../README.md) (with and without Docker) and [DOCKER.md](../DOCKER.md); this
page covers the loop after that.

## Toolchain

| Tool | Version | Source of truth |
|---|---|---|
| Python | 3.12 | `python:3.12-slim` in [`server/Dockerfile`](../server/Dockerfile) |
| Node | 22 | `node:22-alpine` in [`client/Dockerfile`](../client/Dockerfile) |
| MySQL | 8.0 | `mysql:8.0` in [`docker-compose.yml`](../docker-compose.yml) |
| Docker | Compose v2 (`docker compose`) | the prod scripts refuse v1 |

Nothing pins the versions for local runs: there is no `.python-version`, no `.nvmrc`
and no `engines` field. Newer versions are likely fine but untested. On Windows, use
`py` wherever these docs say `python`.

## Three ways to run it

1. **All in Docker.** `docker compose up --build` (or `make up`, which runs detached) →
   <http://localhost:8080>. This is the closest to production, but slow to rebuild: a cold
   build takes several minutes, mostly `npm ci` and Vite.
2. **DB in Docker, code native.** Run `docker compose up -d db`, then `server/.venv`
   running `python run.py` (port 5002), `python run_worker.py`, and `npm run dev` in
   `client/` (port 5174, proxies `/api` to 5002). This is the fastest edit loop. **It
   needs `.env`** (`cp .env.example .env`): the code's DB defaults do not match the
   container. See [README.md](../README.md#running-locally-without-docker).
3. **Run a script inside a container**, to exercise worker code against the stack's
   real data. `/app` is not writable and not on `sys.path` for a script run from
   elsewhere, so:

   ```bash
   docker compose cp x.py worker:/tmp/
   docker compose exec -T -e PYTHONPATH=/app -w /app worker python /tmp/x.py
   ```

To watch a trial reach a verdict in minutes rather than days, set `PHASE_MINUTES=2` in
`.env`. Compose forwards it to both `server` and `worker`. Natively, both processes read
it from `.env`.

## Makefile

`make help` lists every target. All are thin wrappers over compose or the `prod/` scripts.

| Target | Does |
|---|---|
| `make up` | `docker compose up --build -d` |
| `make down` | stop everything, keep the volumes |
| `make clean` | `down -v` after you type `yes`. **Wipes the DB and uploads** |
| `make rebuild` | `build --no-cache`, then `up -d` |
| `make logs [S=server]` | follow logs for one service, or all |
| `make ps` | status and health |
| `make restart S=worker` | restart one service |
| `make seed` | re-run the idempotent seed job |
| `make shell` | bash in the `server` container |
| `make db-shell` | mysql prompt in `db` as the app user |
| `make release VERSION=v…` / `make release-dry VERSION=v…` | `prod/release.sh` (on your machine) |
| `make init-rds`, `make check-rds` | `prod/init-rds.sh`, with `--check` for the second (on EC2) |
| `make deploy VERSION=v…`, `make rollback` | `prod/deploy.sh` (on EC2) |
| `make prod-up`, `prod-down`, `prod-logs [S=…]`, `prod-ps` | compose against `prod/docker-compose.yml` |

## Before you commit

```bash
cd server && python -m pytest --cov        # needs MySQL on 3307 for integration/worker
cd client && npm test && npm run lint      # lint is tsc --noEmit
```

- `npm run lint` is type-checking only; there is no ESLint. `noUnusedLocals` is on, so
  one stray import fails it, and fails the Docker build too (`npm run build` runs `tsc -b`).
- `pytest --cov` enforces `fail_under = 85` from `server/.coveragerc`. A bare `pytest`
  measures nothing.
- `pytest.ini` turns `DeprecationWarning` from `app.*` / `worker.*` into errors, and
  `tests/unit/test_no_deprecated_utcnow.py` bans `datetime.utcnow()`, and
  `tests/unit/test_layering.py` asserts the service layer imports no Flask, since the
  worker has no request context.

Details are in [TESTING.md](../TESTING.md).

## Changing the schema

1. Edit [`database/init.sql`](../database/init.sql). It must stay free of triggers,
   procedures and `DELIMITER` (`tests/integration/test_schema_is_executable.py`), and
   every `CREATE TABLE` stays `IF NOT EXISTS`.
2. Local DB: a new table can be applied in place (see
   [DOCKER.md](../DOCKER.md#resetting-the-database)). A new column needs
   `docker compose down -v` (wipes the data) or a hand-written `ALTER`.
3. For deployed databases, add `prod/migrations/00N-….sql`, document it in the
   migrations tables in [database.md](database.md#migrations) and
   [prod/README.md](../prod/README.md#schema-changes), and say in
   [CHANGELOG.md](../CHANGELOG.md) whether it is idempotent.

## Useful local tools

- **MySQL CLI:** `-ulolsuit -plolsuit-dev` (root: `lolsuit-root-dev`). Pass
  `--default-character-set=utf8mb4`, or Hebrew comes back garbled. That is the CLI's
  doing, not data corruption.
- **Health:** `curl -s localhost:5002/api/health` (direct) or `:8080/api/health` (via
  nginx). Check the worker's `seconds_since_tick` and brain `configured` vs.
  `last_backend` there.
- **Evals:** `cd server && python -m evals.run --no-judge` scores the bots' output. See
  [`server/evals/README.md`](../server/evals/README.md). The judged half is currently
  broken.
- **Untracked local config:** `.claude/launch.json` (starts the Vite dev server),
  `.vscode/` and `postman/` are gitignored, so they exist only on machines that created
  them. The Postman collection points at the wrong port (see
  [known-issues.md](known-issues.md)).

## Releasing

Bump [CHANGELOG.md](../CHANGELOG.md): the major version moves when an upgrade needs a
step beyond pulling the image, such as a migration. Then `./prod/release.sh vX.Y.Z` on
your machine and `./deploy.sh vX.Y.Z` on the instance. See
[prod/README.md](../prod/README.md).
