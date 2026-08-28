# Deploying LolSuit — one EC2 instance + Amazon RDS

```
internet ──80──> [ EC2 ]  web (nginx)  ──/api──>  server (gunicorn)
                                             └─>  worker (scheduler)
                              │
                              └──3306──>  [ Amazon RDS: MySQL 8 ]
```

Three containers on the instance; the data tier is RDS. There is **no database
container** in production — that exists only in the development stack at the repo root.

| File | Runs on | What it is |
|---|---|---|
| [`docker-compose.yml`](docker-compose.yml) | EC2 | The production stack. Pre-built images only — no `build:` anywhere. |
| [`.env.example`](.env.example) | EC2 | Template for `prod/.env`. Copy it, fill it in, `chmod 600`. |
| [`init-rds.sh`](init-rds.sh) | EC2 | Applies the schema to RDS. **Once, before the first deploy.** |
| [`deploy.sh`](deploy.sh) | EC2 | Pull, restart, verify health, roll back if it fails. |
| [`release.sh`](release.sh) | **your Mac** | Build both images, tag them, push to Docker Hub. |

The split matters: **the EC2 box never builds anything.** It has no source tree and no
reason to own a compiler. It pulls images built on a machine that already had the repo.

---

## The 30-second version

On your Mac, after committing:

```bash
./prod/release.sh v1.0.1
```

On the instance:

```bash
cd /opt/lolsuit/prod && ./deploy.sh v1.0.1
```

Everything below is what those two commands do, and what to do when one fails.

---

## First-time setup

### 1. The security groups — get this right and most problems disappear

Two groups, and the second one is where nearly every "it just hangs" ends up.

**EC2 instance SG** (inbound):

| Port | Source | Why |
|---|---|---|
| 80 | `0.0.0.0/0` | The site |
| 443 | `0.0.0.0/0` | Only once you add TLS |
| 22 | **your IP only** | SSH. Never `0.0.0.0/0`. |

**RDS instance SG** (inbound):

| Port | Source | Why |
|---|---|---|
| 3306 | **the EC2 instance's security group _id_** | The app |

Reference the EC2 security group *by id* (`sg-0abc…`), not by IP address. An IP rule
breaks the moment the instance is stopped and started, because the public IP changes —
and the failure looks exactly like a credentials problem.

**RDS must not be publicly accessible.** Set "Public access: No" and keep it in the same
VPC as the instance. Nothing outside needs to reach it; you can always tunnel:

```bash
ssh -L 3307:YOUR_RDS_ENDPOINT:3306 ec2-user@YOUR_EC2_HOST
```

### 2. Prepare the instance

Install Docker Engine and the Compose v2 plugin. The hyphenated `docker-compose` v1 is
end-of-life and does **not** support the `pull_policy` and `depends_on.condition` keys
this stack relies on:

```bash
curl -fsSL https://get.docker.com | sh
```

Let your user drive Docker without `sudo` — log out and back in for it to take effect:

```bash
sudo usermod -aG docker "$USER"
```

Get the repo onto the box. `prod/` plus `database/init.sql` is all that is strictly
needed, but a plain clone is simpler and keeps `git pull` available:

```bash
sudo mkdir -p /opt/lolsuit && sudo chown "$USER" /opt/lolsuit
git clone https://github.com/Avi-Lezerovich/fullstack-2026.git /opt/lolsuit
```

### 3. Write `prod/.env`

```bash
cd /opt/lolsuit/prod && cp .env.example .env && chmod 600 .env
```

`chmod 600` is not decoration — the file holds your RDS password.

Fill in at minimum `DOCKERHUB_USERNAME`, `DB_HOST`, `DB_PASSWORD` and `CLIENT_ORIGIN`.
The compose file declares these as `${VAR:?…}`, so a missing one **aborts the deploy**
rather than quietly booting with a development password. That `?` is the most important
character in the file.

`DB_HOST` is a bare hostname — no scheme, no port:

```
lolsuit.abc123xyz.eu-central-1.rds.amazonaws.com
```

> **While you are still on plain HTTP** (the EC2 public DNS, no certificate), set
> `FLASK_SESSION_SECURE=0`. A `Secure` cookie is never sent over `http://`, so login
> appears to succeed and then every subsequent request is anonymous. Flip it to `1` the
> moment TLS is in front.

### 4. Bootstrapping the RDS schema

**This is the step that has no equivalent in the dev stack, and skipping it is the most
likely way your first deploy fails.**

With a MySQL *container*, Docker's entrypoint applies `database/init.sql` automatically.
RDS has no such hook — a fresh instance is an empty database. So, once:

```bash
cd /opt/lolsuit/prod && ./init-rds.sh
```

It borrows the `mysql` client from the official image, so nothing needs installing on the
instance. Check connectivity without changing anything:

```bash
cd /opt/lolsuit/prod && ./init-rds.sh --check
```

It is **safe to re-run**: all 18 `CREATE TABLE` statements are `IF NOT EXISTS`.

For exactly that reason it is **not a migration tool** — `IF NOT EXISTS` can only ever
*add* a table, never add a column to an existing one. See "Schema changes" below.

### 5. First deploy

```bash
cd /opt/lolsuit/prod && ./deploy.sh v1.0.1
```

The seed job runs automatically and creates the 19 court bots, the demo accounts and the
opening case. It is idempotent, so it runs safely on every deploy.

---

## Releasing a new version

From the repo root, on your Mac:

```bash
./prod/release.sh v1.0.1
```

> **Your Mac is arm64; your EC2 instance is x86_64.** A plain `docker build && docker
> push` publishes an arm64 image that pulls fine and then dies instantly with
> `exec /usr/local/bin/gunicorn: exec format error`. `release.sh` never calls
> `docker build` — it uses `buildx` with an explicit `--platform linux/amd64`, so this
> cannot happen by accident. (On Graviton, use
> `PLATFORMS=linux/amd64,linux/arm64`.)

The script:

1. refuses anything that is not `vMAJOR.MINOR.PATCH`;
2. refuses to build from a dirty tree — a published image should be rebuildable from its
   git sha, and from a dirty tree it would not be;
3. cross-builds both images for `linux/amd64`;
4. stamps `VERSION`, `GIT_SHA` and `BUILD_DATE` into OCI labels;
5. pushes `:v1.0.1` and `:latest` for each image.

Variations:

```bash
./prod/release.sh v1.0.1 --dry-run     # print the buildx commands, build nothing
```

```bash
./prod/release.sh v1.0.2 --web-only    # frontend-only fix; skip the API image
```

```bash
./prod/release.sh v1.0.1 --git-tag     # also create and push an annotated git tag
```

### Which commit is actually running?

The tag can lie; the label cannot:

```bash
docker image inspect $(docker compose -f prod/docker-compose.yml images -q server) --format '{{index .Config.Labels "org.opencontainers.image.revision"}}'
```

---

## Deploying

### The recommended way

```bash
cd /opt/lolsuit/prod && ./deploy.sh v1.0.1
```

In this order, for these reasons:

1. **Rewrites `TAG=` in `prod/.env`** so the file always records what is live — and the
   previous value is what a rollback returns to.
2. **Pulls the new images while the old ones keep serving.** The slow step, at *zero*
   downtime.
3. **Recreates the containers.** Seconds, because the bytes are already local. This also
   waits for the seed job to exit 0.
4. **Waits for `/api/health`** through nginx, up to `HEALTH_TIMEOUT` (120s).
5. **Rolls back automatically** if it never becomes healthy, restoring both `.env` and
   the running containers.
6. **Appends to `.deploy-history`** — one line per deploy, which `--rollback` reads.
7. **Prunes dangling images.** Note `image prune -f`, not `-a`: tagged images are kept,
   so the previous version stays on disk and a rollback needs no download.

### The same thing by hand

```bash
cd /opt/lolsuit/prod
```

```bash
sed -i "s/^TAG=.*/TAG=v1.0.1/" .env
```

```bash
docker compose -f docker-compose.yml pull
```

```bash
docker compose -f docker-compose.yml up -d --remove-orphans
```

```bash
docker compose -f docker-compose.yml ps
```

`pull` **before** `up -d`. Reversing them stops the containers and only *then* starts
downloading 250MB — turning seconds of downtime into minutes.

You do not need `--env-file`: Compose reads `.env` from the *project directory* — the
one holding the compose file — so `prod/.env` is found even when you run from the repo
root.

### Rolling back

```bash
cd /opt/lolsuit/prod && ./deploy.sh --rollback
```

Or explicitly, which is always safe:

```bash
cd /opt/lolsuit/prod && ./deploy.sh v1.0.0
```

Rollback covers the *application*. It does **not** undo a schema change — which is the
main reason to keep migrations additive and backwards-compatible for one release.

---

## How much downtime, honestly

**Roughly two to five seconds**, and only for services whose image actually changed.
Compose compares each service's image digest and configuration and recreates only what
differs — a frontend-only release does not restart the API.

That is *minimal* downtime, not *zero*. Plain `docker compose` cannot do a true
zero-downtime swap of a service publishing a fixed host port, because exactly one
container can hold `0.0.0.0:80` at a time. Anyone claiming otherwise with this toolset is
glossing over that.

Since RDS is external, a deploy never restarts the database — which is the part that
would actually hurt.

If those seconds matter:

- **Put a proxy in front** (Caddy, Traefik, host nginx), run two `web` containers on
  unpublished ports, and drain one before recreating it.
- **Move to an orchestrator** with rolling updates as a first-class feature — ECS is the
  natural next step on AWS. That is the point at which Compose is the wrong tool, not a
  broken one.

The API is already better placed: `server` sits behind nginx on an internal network and
`worker` serves no HTTP, so in-flight requests keep landing if you scale before
recreating:

```bash
docker compose -f docker-compose.yml up -d --scale server=2 --no-recreate
```

---

## Putting HTTPS in front

The stack deliberately does not terminate TLS. In `prod/.env`, stop Compose owning port
80:

```bash
WEB_PUBLISH_BIND=127.0.0.1
WEB_PUBLISH_PORT=8080
```

Open 443 in the EC2 security group, point a domain at the instance (an Elastic IP, so it
survives a stop/start), and let Caddy handle the certificate:

```
lolsuit.example.com {
	reverse_proxy 127.0.0.1:8080
}
```

Then, in `prod/.env`:

```bash
FLASK_SESSION_SECURE=1
CLIENT_ORIGIN=https://lolsuit.example.com
```

> **SSE note.** The app streams notifications over `/api/notifications/stream`. Caddy
> handles this by default; a hand-rolled nginx front-end needs `proxy_buffering off` for
> that location, or notifications arrive in bursts. The bundled nginx already does this —
> this applies only to a *second* proxy you put in front.

---

## Operating it

### Logs

Capped at 10MB × 5 files per service. Unbounded `json-file` logs are the most common way
a small instance fills its root volume and takes the site down.

```bash
docker compose -f prod/docker-compose.yml logs -f server
```

### Health

```bash
curl -s http://YOUR_HOST/api/health | python3 -m json.tool
```

`"status": "ok"`, `"database": "up"`, and a `worker` block whose `seconds_since_tick`
keeps resetting. It answers **503**, not 500, while MySQL is unreachable — which is what
the container healthcheck keys on.

### Backups

RDS handles the database: enable **automated backups** and set the retention window in
the console. That is the main reason to be on RDS at all. A manual dump:

```bash
docker run --rm -e MYSQL_PWD="$DB_PASSWORD" mysql:8.0 mysqldump -h "$DB_HOST" -u "$DB_USER" "$DB_NAME" | gzip > "lolsuit-$(date +%F).sql.gz"
```

**Uploads are the one piece of state RDS does not cover.** Avatars and evidence photos
live in a named Docker volume on the instance's EBS root device. They are not in your RDS
snapshots and do not survive replacing the instance:

```bash
docker run --rm -v lolsuit_uploads:/data -v "$PWD:/backup" alpine tar czf /backup/uploads-$(date +%F).tar.gz -C /data .
```

Check the real volume name first — Compose prefixes it with the project name:

```bash
docker volume ls | grep uploads
```

For anything long-lived, move uploads to S3 and stop worrying about the instance.

### Schema changes

`init-rds.sh` only ever *adds missing tables*. Changing an existing table is deliberate
SQL you write and apply, after a backup:

```bash
docker run --rm -i -e MYSQL_PWD="$DB_PASSWORD" mysql:8.0 mysql -h "$DB_HOST" -u "$DB_USER" "$DB_NAME" < migration.sql
```

Take an RDS snapshot first. Every time.

### A least-privilege database user

The RDS master account works, but the app needs far less. Once, as master:

```sql
CREATE USER 'lolsuit'@'%' IDENTIFIED BY 'a-strong-password';
GRANT SELECT, INSERT, UPDATE, DELETE ON lolsuit.* TO 'lolsuit'@'%';
```

Grant `CREATE, ALTER, INDEX, REFERENCES` temporarily when you run `init-rds.sh`, then
revoke them. Day to day the application never issues DDL — `create_app()` is deliberately
side-effect free.

---

## When it goes wrong

| Symptom | Cause | Fix |
|---|---|---|
| `exec format error` | arm64 image on x86 EC2 | Rebuild with `release.sh` (pins `linux/amd64`) |
| `up -d` hangs for ~6 min, then seed fails | Cannot reach RDS | `./init-rds.sh --check`. Almost always the RDS security group |
| `required variable DB_PASSWORD is missing` | Working as designed | Fill it in in `prod/.env` |
| `Table 'lolsuit.users' doesn't exist` | Schema never applied | Run `./init-rds.sh` |
| `pull access denied` | Not logged in, or tag never pushed | `docker login`; check the tag on Docker Hub |
| Login works, then everything is anonymous | `FLASK_SESSION_SECURE=1` on plain HTTP | Set it to `0`, or finish setting up TLS |
| Site up, API 502 | `server` unhealthy, nginx has no upstream | `logs server` — usually a database credential |
| Uploads vanished | Instance replaced, or the volume removed | Restore from backup; consider S3 |
| `docker-compose: command not found` | Compose v1 | Install the Compose v2 plugin |

Start here, whatever the symptom:

```bash
docker compose -f prod/docker-compose.yml ps
```

```bash
docker compose -f prod/docker-compose.yml logs --tail=100
```
