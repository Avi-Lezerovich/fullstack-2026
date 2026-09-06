# Testing

Automated tests for LolSuit, organised as a **test pyramid** and following
**AAA** (Arrange → Act → Assert) — though the assertions are grouped by blank
lines rather than by comment, which is what the suite settled on.

| Layer | Marker | Count | Needs | What it checks |
|-------|--------|-------|-------|----------------|
| **Unit** | `unit` | 486 | nothing | Pure logic in isolation — password hashing and the length rule bcrypt 5 enforces, cookie flags, the sentiment lexicon, jury selection and tallying, trial-clock arithmetic, the SQL a service sends and the parameters bound to it, and the layering rules the other layers rely on. |
| **Integration** | `integration` | 465 | MySQL | The real Flask endpoints and the real service layer against a real MySQL schema built from `database/init.sql` — sessions, password resets, the four moderation statuses, content visibility, messages, witnesses, uploads, and the permission matrix on every endpoint. |
| **Worker** | `worker` | 69 | MySQL | The trial state machine end to end, the three moderator bots, the social bots, and the idempotency guarantee: a tick run twice reaches the same state as a tick run once. Also carry `integration`, so they are counted in the row above. |
| **Frontend** | — | 136 | nothing | vitest + @testing-library/react over the client's hooks, context and the components with real logic. |

951 backend tests in total. Every one carries a layer marker — the worker tests
carry both `worker` and `integration`, which is why the three counts add to more
than 951 — so `-m unit` and `-m "integration or worker"` between them run the
whole suite and nothing twice.

Backend coverage: **95.5%** across `app` and `worker` (gate: 85%, set in
`server/.coveragerc` and applied whenever the run is measured — see `--cov` below).

---

## Prerequisites

- **Python** — on this Windows box use the `py` launcher; the bare `python`
  command is shadowed by the Windows Store alias stub.
- **Docker Desktop** — for MySQL. The unit layer runs without it.

```powershell
py -m pip install -r server/requirements-dev.txt
npm --prefix client install
```

---

## Backend

```powershell
docker compose up -d db
```

```powershell
cd server
py -m pytest --cov
```

`--cov` is the one flag to remember: `pytest.ini` does not carry it, so a bare
`py -m pytest` runs the suite without measuring anything and without the gate.
Everything past the flag lives in `.coveragerc` — which packages to measure, the
85% `fail_under`, and `show_missing`, so the uncovered lines are already in that
output and there is no `--cov-report` to add.

Without coverage, which is what you want while iterating:

```powershell
cd server
py -m pytest
```

One layer at a time:

```powershell
cd server
py -m pytest -m unit
py -m pytest -m integration
py -m pytest -m worker
```

### How the harness works

`tests/conftest.py` builds the schema itself rather than mirroring it:

1. connects to the dev MySQL as root and creates a throwaway `lolsuit_test`
   database — **your `lolsuit` database is never touched**;
2. reads `database/init.sql`, strips comments, splits on `;` and executes each
   statement. That is only possible while the file stays free of triggers,
   stored procedures and `DELIMITER` blocks, which
   `tests/integration/test_schema_is_executable.py` asserts;
3. sets the environment before any application import — `BCRYPT_ROUNDS=4`,
   `MAIL_BACKEND=console` (the repo's real `.env` carries live SMTP
   credentials), `BRAIN_FORCE_OFFLINE=1`, and a one-minute trial "day";
4. runs `app.seed` once, because the worker tasks need the thirty-one court
   personalities to do anything at all;
5. deletes everything but the cast before each test.

No monkeypatching is involved. `app/config.py` re-reads the environment on every
`get_settings()` call, so pointing `DB_NAME` at the test database redirects the
services, the API *and* the worker's own `connect()` at once.

**Without MySQL running**, everything marked `integration` or `worker` skips with
a reason naming `docker compose up -d db`, and the unit layer still runs. The
95.5% figure assumes the database is up.

Overridable: `TEST_DB_HOST`, `TEST_DB_PORT`, `TEST_DB_ROOT_USER`,
`TEST_DB_ROOT_PASSWORD`, `TEST_DB_NAME`.

### Why real MySQL and not SQLite

The previous harness mirrored the schema by hand in SQLite and rewrote the
application's SQL on the way through. `app/db.py` opens with what that cost:

> Placeholders are MySQL's own `%s`. There is no `?` translation layer. The
> previous generation of this project had one, and it was exactly what made
> running the test suite against SQLite look reasonable — which in turn meant
> the tests never exercised the dialect the application actually speaks.

Most of what this application guarantees is enforced by the database rather than
by Python: the four moderation statuses are an `ENUM`, one-like-per-user is a
composite `PRIMARY KEY`, one-report-per-person is a `UNIQUE` index, the trial
engine's idempotency is `FOR UPDATE SKIP LOCKED` plus a `UNIQUE` index over a
nullable column, and every deadline is written and compared with
`UTC_TIMESTAMP()` so two processes cannot disagree. A mirror can only agree with
those; it cannot check them.

---

## Frontend

```powershell
npm --prefix client test
npm --prefix client run lint
npm --prefix client run test:coverage
```

`lint` is `tsc --noEmit`; there is no ESLint in this project. `tsconfig.json` sets
`noUnusedLocals`, so an unused import in a test file fails the typecheck.

Tests aim at the pieces with real logic rather than at markup:

- **`usePagedList`** — offset accumulation, the stale-response token, the
  empty-later-page rule, and `patchItems`;
- **`useAsync`** — the same stale guard in its other shape;
- **`AuthContext`** — `loading` until `/auth/me` settles, a failed probe meaning
  anonymous, and `signOut` clearing the user even when the request throws;
- **`useNotificationStream`** — one failure reconnects, two inside thirty seconds
  fall back to polling permanently, and both transports share one cursor;
- **`LikeButton` / `FollowButton`** — the guarded prop-sync, including the round
  trip where the parent hands the server's answer straight back as props;
- **`CommentThread`**, **`CaseCard`**, **`InfiniteScroll`**, **`ErrorPage`**,
  **`AppErrorBoundary`** — that it keeps the chrome around a thrown render and
  clears itself on navigation — **`ProtectedRoute`** and **`utils/format`**.

There is no coverage gate on the client. The page components are deliberately
untested: they are markup over the hooks above, and asserting on their DOM would
add numbers rather than confidence.

Two route-level files are a narrow, deliberate exception, because what they pin
is behaviour rather than markup:

- **`src/App.test.tsx`** — that an unknown address renders the 404 page instead
  of silently redirecting to the feed. The claim is about the routing table, so
  it is asserted through the real `App`.
- **`src/pages/ResetPassword.test.tsx`** — that the form is not drawn until the
  server has confirmed the reset link is still live. The bug it prevents cost the
  user two password entries before telling them the link was dead.

---

## Known gaps

- **`app/brain/llm.py`** sits at 81%, and is the only file materially below the
  rest. The remainder is live-network provider code, which the suite never
  calls: `BRAIN_FORCE_OFFLINE=1` throughout, so no test reaches a model backend.
- **`worker/social_tasks.py`** sits at 84%. What is left is the branches where a
  model writes a filing — the offline generator takes a different path through
  `_lawsuit_target`, so those lines need a configured provider to reach.
- **`cases.defendant_user_id` has no foreign key.** `database/init.sql` documents
  an `ON DELETE SET NULL` constraint on it at length and never declares it, so
  deleting a user leaves the filing pointing at an id that is gone. Latent —
  nothing in the application deletes a user — and recorded as a strict `xfail` in
  `tests/integration/test_case_withdrawal.py`, which will start failing the day
  the constraint is added.
