# Testing — User Authentication & Post Deletion

Automated tests for the auth feature (sign-up, login, logout, password hashing)
and the delete-post feature (owner-only post deletion), organised as a
**test pyramid** and following **AAA** (Arrange → Act → Assert).

| Layer | Count | Tool | What it checks |
|-------|-------|------|----------------|
| **Unit** | 20 | pytest | `hash_password` / `verify_password` / `session_cookie_flags` / `get_session_token` in isolation (no DB, no network); `delete_post`'s ok/forbidden/not_found/cascade branches against an in-memory SQLite connection |
| **Integration** | 16 | pytest + Flask test client | sign-up / login / logout / `require_auth` through the real endpoints; `DELETE /api/posts/<id>` ownership (owner/forbidden/not-found/unauthenticated) |
| **E2E** | 2 | Cypress | sign up → log out → log in → view profile; sign up → create post → delete post, both in a real browser |

Coverage on the authentication code (`app/utils.py`, `app/services.py`, `app/routes.py`): **100%** (gate: 85%).

---

## Prerequisites

- **Python** — on this Windows box use the `py` launcher (the bare `python` command is
  shadowed by the Windows Store alias stub).
- **Docker Desktop** — only needed for the E2E (it runs MySQL).

Install test dependencies once:

```powershell
py -m pip install -r server/requirements-dev.txt   # pytest, pytest-cov
npm --prefix client install                        # includes Cypress
```

---

## Unit + integration (pytest)

Run from the `server/` directory so `pytest.ini` and `.coveragerc` are picked up:

```powershell
cd server
py -m pytest -v                                    # all 36 backend tests
py -m pytest -m unit                               # just the unit layer
py -m pytest -m integration                        # just the integration layer
py -m pytest --cov=app --cov-report=term-missing   # with the coverage report
```

These need **no database** — `tests/conftest.py` injects a throwaway SQLite DB into
the app (via `services.get_db`) and drives the real Flask endpoints with the test
client. Fast, hermetic, repeatable.

**Known SQLite/MySQL parity limits** (deliberate, and covered by the E2E, which
runs against real MySQL): the literal `ON DUPLICATE KEY UPDATE` upsert in
`create_session` and the production `?` → `%s` placeholder rewrite
(`app/models.py`) never execute under pytest — the SQLite adapter substitutes
equivalents. FK enforcement is switched ON in the fixture to match InnoDB.

**Coverage is scoped to the auth code.** `server/.coveragerc` reports only the three
auth-bearing files and uses `exclude_also` to drop the non-auth functions (posts,
follows, profiles, uploads) from the denominator, so the 85% gate measures
authentication specifically — not a whole-repo average. `fail_under = 85` enforces it.

## End-to-end (Cypress)

The E2E drives the real stack, so start all three services first:

```powershell
# 1) MySQL
docker compose up -d db

# 2) Flask API on :5001 (point it at the local MySQL)
$env:DB_HOST="localhost"; $env:DB_PORT="3306"; $env:DB_USER="root"
$env:DB_PASSWORD="change-me-in-production"; $env:DB_NAME="lolsuit"
py server/run.py

# 3) Vite client on :5173 (in another shell)
npm --prefix client run dev

# 4) Run the spec (in another shell)
npm --prefix client run cypress:run     # headless
npm --prefix client run cypress:open    # interactive runner
```

Notes:
- The client uses **HashRouter**, so routes live under the URL fragment (`#/signup`,
  `#/user-posts/:id`); the spec navigates by hash / through the UI accordingly.
- Each spec uses a **unique email/post title per run**, so it stays repeatable against
  the persistent MySQL database (each run leaves one throwaway user, and the delete-post
  spec cleans up its own post — harmless either way).
- Selectors use `data-testid` attributes added to the auth form fields and nav, plus the
  new-post form and the post card's delete button/confirm dialog.

Tear down when done: `docker compose stop db` (keep data) or `docker compose down -v`
(wipe the DB volume).
