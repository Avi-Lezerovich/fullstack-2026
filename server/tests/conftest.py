# -*- coding: utf-8 -*-
"""The test harness: a real MySQL schema, built from database/init.sql.

The previous version of this file mirrored the schema by hand in SQLite and
monkeypatched `app.services.get_db`. Both anchors are gone - there is no
`get_db` seam any more, and `app/db.py` opens with the reason the mirror was a
mistake in the first place:

    "Placeholders are MySQL's own %s. There is no ? translation layer. The
     previous generation of this project had one, and it was exactly what made
     running the test suite against SQLite look reasonable - which in turn
     meant the tests never exercised the dialect the application actually
     speaks."

So this harness executes `database/init.sql` itself, verbatim, into a throwaway
database. That is the property the schema file's own header promises, and it is
what lets these tests exercise the real FKs, the real ENUM constraints,
`FOR UPDATE SKIP LOCKED`, `ON DUPLICATE KEY UPDATE` and `UTC_TIMESTAMP()`
rather than an approximation of them.

**Why no monkeypatching is needed.** `app/config.py` re-reads the environment on
every `get_settings()` call, deliberately. Pointing `DB_NAME` at the test
database once, at import time, therefore redirects the services, the API *and*
the worker's own `connect()` - all three - with no seam to patch and no chance
of the web half and the worker half disagreeing about which database they are
in.

**Why the environment is set at module scope** rather than in a fixture: pytest
imports conftest before it imports any test module, and a test module importing
`app` is what triggers `load_dotenv()`. `load_dotenv` never overrides a
variable that is already set, so getting in first is the whole trick - and it
is what keeps the repo's real `.env` (which carries live SMTP credentials and
`MAIL_BACKEND=smtp`) from being used by a test that asks for a password reset.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
INIT_SQL = _REPO_ROOT / "database" / "init.sql"

# --- the test database ------------------------------------------------------
#
# root, not the application user: `lolsuit` has rights on its own database and
# nowhere else, and this needs to CREATE one. The application still connects as
# whatever DB_USER says below - it simply happens to be root here too, because
# a test database nobody else can see does not need a second account.

TEST_DB_HOST = os.environ.get("TEST_DB_HOST", "127.0.0.1")
TEST_DB_PORT = int(os.environ.get("TEST_DB_PORT", "3307"))
TEST_DB_USER = os.environ.get("TEST_DB_ROOT_USER", "root")
TEST_DB_PASSWORD = os.environ.get("TEST_DB_ROOT_PASSWORD", "lolsuit-root-dev")
TEST_DB_NAME = os.environ.get("TEST_DB_NAME", "lolsuit_test")


def _configure_environment() -> None:
    """Everything the application reads, fixed before the first app import."""
    os.environ["DB_HOST"] = TEST_DB_HOST
    os.environ["DB_PORT"] = str(TEST_DB_PORT)
    os.environ["DB_USER"] = TEST_DB_USER
    os.environ["DB_PASSWORD"] = TEST_DB_PASSWORD
    os.environ["DB_NAME"] = TEST_DB_NAME

    # The one setting config.py marks as "only ever lowered by the test suite".
    # Twelve rounds is ~250ms per hash; a suite that signs up hundreds of users
    # would spend minutes doing nothing else.
    os.environ["BCRYPT_ROUNDS"] = "4"

    # Nothing here may reach the network. The repo's .env sets MAIL_BACKEND=smtp
    # with live credentials, and the password-reset tests send mail by design.
    os.environ["MAIL_BACKEND"] = "console"
    os.environ["BRAIN_FORCE_OFFLINE"] = "1"

    # A trial "day" of one minute, so a lifecycle test can move a deadline into
    # the past and tick rather than waiting on the real calendar.
    os.environ["PHASE_MINUTES"] = "1"
    os.environ["SSE_POLL_SECONDS"] = "0.01"
    os.environ["SSE_MAX_SECONDS"] = "0.05"

    # Deterministic jury draws.
    os.environ["JURY_SEED_SALT"] = "lolsuit-test"


_configure_environment()


# --- executing database/init.sql --------------------------------------------


def statements_in(sql: str) -> list[str]:
    """Split the schema file into executable statements.

    Comments are stripped first, and that is not merely tidy: the header's own
    prose mentions "triggers, stored procedures and DELIMITER blocks" by name,
    so a purity check that did not strip comments would fail on the sentence
    promising the property it is checking.

    Splitting on `;` is only safe while the file stays free of DELIMITER blocks
    and semicolons inside string literals. Both are asserted by
    tests/integration/test_schema_is_executable.py, which is the test the
    header claims exists.
    """
    without_comments = "\n".join(re.sub(r"--.*$", "", line) for line in sql.splitlines())
    return [statement.strip() for statement in without_comments.split(";") if statement.strip()]


def _connect_raw(database: str | None = None):
    import pymysql
    from pymysql.cursors import DictCursor

    return pymysql.connect(
        host=TEST_DB_HOST,
        port=TEST_DB_PORT,
        user=TEST_DB_USER,
        password=TEST_DB_PASSWORD,
        database=database,
        charset="utf8mb4",
        cursorclass=DictCursor,
        autocommit=True,
    )


def _database_is_reachable() -> str | None:
    """None when MySQL answers, otherwise the reason it did not."""
    try:
        _connect_raw().close()
        return None
    except Exception as exc:  # pragma: no cover - only on a machine with no db
        return f"{type(exc).__name__}: {exc}"


_UNREACHABLE = _database_is_reachable()


def needs_a_database(item) -> bool:
    """Whether this test carries the integration or worker marker.

    Asked through the marker API rather than with `"worker" in item.keywords`,
    which looked equivalent and was not: `keywords` also holds every
    parametrize id, so `test_module_imports[worker]` - a hermetic unit test
    that imports the `worker` package by name - matched and was skipped
    whenever the database was down.
    """
    return any(marker.name in ("integration", "worker") for marker in item.iter_markers())


def pytest_collection_modifyitems(config, items):
    """Skip the layers that need a database, rather than erroring in a fixture.

    The unit layer is hermetic and must still run on a machine with no Docker.
    The skip reason names the command, because "connection refused" four
    hundred times over is not a useful answer to "why did my suite not run".
    """
    if _UNREACHABLE is None:
        return
    skip = pytest.mark.skip(
        reason=(
            f"no MySQL on {TEST_DB_HOST}:{TEST_DB_PORT} ({_UNREACHABLE}). "
            "Start it with: docker compose up -d db"
        )
    )
    for item in items:
        if needs_a_database(item):
            item.add_marker(skip)


# --- the schema, once per session -------------------------------------------

# Tables whose contents ARE the fixture: the thirty-one court personalities and
# the users they hang off. Rebuilding them per test would mean bcrypt-hashing
# and re-inserting the whole cast hundreds of times.
_KEEP = {"users", "agents", "worker_state"}


@pytest.fixture(scope="session")
def _schema():
    """Drop, rebuild from init.sql, seed the cast. Returns the user watermark.

    The watermark is the highest user id the seed created. Everything above it
    is a test's own user and is deleted between tests; everything at or below
    it is the permanent cast, which the worker tasks need in order to do
    anything at all - `moderator_id("clerk")` returning None makes every
    moderation task a no-op that asserts nothing.
    """
    if _UNREACHABLE is not None:  # pragma: no cover - collection already skipped
        pytest.skip(_UNREACHABLE)

    server = _connect_raw()
    with server.cursor() as cur:
        cur.execute("DROP DATABASE IF EXISTS `" + TEST_DB_NAME + "`")
        cur.execute(
            "CREATE DATABASE `" + TEST_DB_NAME + "` "
            "DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        )
    server.close()

    conn = _connect_raw(TEST_DB_NAME)
    with conn.cursor() as cur:
        for statement in statements_in(INIT_SQL.read_text(encoding="utf-8")):
            cur.execute(statement)
    conn.close()

    from app import seed

    seed.main()

    conn = _connect_raw(TEST_DB_NAME)
    with conn.cursor() as cur:
        cur.execute("SELECT MAX(id) AS watermark FROM users")
        watermark = int(cur.fetchone()["watermark"])
        cur.execute("SHOW TABLES")
        tables = [next(iter(row.values())) for row in cur.fetchall()]
    conn.close()

    return {"watermark": watermark, "tables": tables}


@pytest.fixture(autouse=True)
def _clean(request):
    """Return the database to the seeded state before every test that uses one.

    Deleting rather than rolling back a transaction, because the worker tasks
    open their own connections and commit on them - by design, so that one
    failing case cannot abort a whole tick. A rollback in the test's own
    connection would not reach any of that.

    Gated on the marker, and that gate is worth more than it looks: the unit
    layer is several hundred tests that never open a connection, and making
    each of them wait on twenty DELETEs first turned a two-second suite into a
    three-minute one.
    """
    if not needs_a_database(request.node):
        yield
        return

    _schema = request.getfixturevalue("_schema")
    conn = _connect_raw(TEST_DB_NAME)
    with conn.cursor() as cur:
        cur.execute("SET FOREIGN_KEY_CHECKS = 0")
        # DELETE rather than TRUNCATE. TRUNCATE drops and recreates the
        # tablespace, which for twenty-odd InnoDB tables before every single
        # test cost more than the tests did. DELETE on an already-empty table
        # is nearly free, and most of these are empty most of the time.
        #
        # The visible difference is that AUTO_INCREMENT counters keep climbing
        # instead of resetting to 1. That is the better default anyway: a test
        # that passes only because the first case is always id 1 is a test
        # about the harness.
        for table in _schema["tables"]:
            if table not in _KEEP:
                cur.execute("DELETE FROM `" + table + "`")
        # The cast survives; anything a test signed up does not.
        cur.execute("DELETE FROM users WHERE id > %s", (_schema["watermark"],))
        # A test that bans a seeded account must not leave it banned.
        cur.execute(
            "UPDATE users SET status = 'active', banned_at = NULL WHERE id <= %s",
            (_schema["watermark"],),
        )
        cur.execute(
            "UPDATE worker_state SET tick_count = 0, last_tick_at = NULL, last_error = NULL"
        )
        # The cast's rows survive, but not the worker's pacing state on them.
        # `last_social_action_at` is what decides whose turn it is, and the
        # seed deliberately leaves it alone on re-run - so without this a test
        # that let the bots act would hand the next one a cast that had all
        # just moved, and "whose turn is it" would depend on execution order.
        cur.execute("UPDATE agents SET last_social_action_at = NULL, is_active = 1")
        cur.execute("SET FOREIGN_KEY_CHECKS = 1")
    conn.close()
    yield


# --- what a test actually asks for ------------------------------------------


@pytest.fixture
def db(_schema):
    """A raw `Db` on the test schema, for driving services and for observing.

    Closed afterwards; not committed for the caller, because half these tests
    are about who commits what.

    **READ COMMITTED, not the server's REPEATABLE READ default**, and the
    reason is that this connection is unlike any the application ever opens.
    Production takes a fresh connection per request and per worker task, so it
    always reads current data. This one lives for a whole test, and under
    REPEATABLE READ its snapshot is fixed at its first read - so a test that
    checks a row, posts through the Flask client (a *different* connection),
    and looks again would still see the old value and fail for a reason that
    exists nowhere outside the harness.

    Lowering it here restores per-statement freshness without giving up
    transactions, so `conn=db` still means "the caller owns this transaction"
    exactly as the service layer's convention requires.
    """
    from app.db import connect

    connection = connect()
    connection.execute("SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED")
    connection.commit()
    yield connection
    connection.close()


@pytest.fixture
def app(_schema):
    from app import create_app

    flask_app = create_app()
    flask_app.config.update(TESTING=True)
    return flask_app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def make_user(db):
    """Insert a user directly and return the row.

    Deliberately not through `POST /auth/signup`: a test about moderation
    should not fail because the signup validator changed, and a banned or admin
    account has no endpoint that creates it.
    """
    from app.security import hash_password
    from app.services import users_service

    created = 0

    def _make(
        name: str = "עד המדינה",
        email: str | None = None,
        *,
        password: str = "correct-horse",
        is_admin: bool = False,
        is_bot: bool = False,
        status: str = "active",
    ) -> dict:
        nonlocal created
        created += 1
        address = email or f"user{created}@lolsuit.test"
        db.execute(
            "INSERT INTO users (name, email, password_hash, is_admin, is_bot, status, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, UTC_TIMESTAMP())",
            (name, address, hash_password(password), int(is_admin), int(is_bot), status),
        )
        db.commit()
        row = users_service.get_by_email(address, conn=db)
        # The plaintext is not on the row and every caller that signs in needs
        # it, so it rides along rather than being re-derived from a convention.
        row["password"] = password
        return row

    return _make


@pytest.fixture
def admin(make_user):
    return make_user("שופטת ראשית", "admin@lolsuit.test", is_admin=True)


@pytest.fixture
def signed_in(client):
    """Log a user in on the shared test client and hand back the raw token.

    Goes through the real endpoint so the cookie is set exactly as a browser
    would receive it - which is the point of an integration test, and the only
    way `require_auth` is genuinely exercised.
    """

    def _sign_in(user: dict) -> str:
        response = client.post(
            "/api/auth/login",
            json={"email": user["email"], "password": user["password"]},
        )
        assert response.status_code == 200, response.get_json()
        return client.get_cookie("session_id").value

    return _sign_in


@pytest.fixture
def make_case(db):
    """File a case, bypassing the moderation scan.

    `screen=False` for the same reason `app.seed` uses it: a visibility test
    should decide the moderation_status itself rather than inheriting whatever
    the lexicon thinks of its Hebrew fixture text.
    """
    from app.services import cases_service

    filed = 0

    def _make(
        author_id: int,
        *,
        title: str | None = None,
        body: str = "הנתבע לקח את החניה שלי ואמר שזה בסדר.",
        defendant_text: str = "השכן מקומה 3",
        charges: list[str] | None = None,
        moderation_status: str = "published",
        status: str | None = None,
    ) -> int:
        nonlocal filed
        filed += 1
        result, case_id = cases_service.create_case(
            author_id,
            title or f"תביעה מספר {filed}",
            body,
            defendant_text,
            charges=charges or ["גרימת עוגמת נפש"],
            moderation_status=moderation_status,
            screen=False,
            conn=db,
        )
        assert result == "ok", result
        if status is not None:
            db.execute("UPDATE cases SET status = %s WHERE id = %s", (status, case_id))
        db.commit()
        return case_id

    return _make


@pytest.fixture
def make_comment(db):
    """Post a comment, likewise unscreened."""
    from app.services import comments_service

    def _make(
        case_id: int,
        author_id: int,
        *,
        body: str = "גם לי זה קרה, ואף אחד לא עשה כלום.",
        parent_comment_id: int | None = None,
        moderation_status: str = "published",
    ) -> int:
        result, comment_id = comments_service.create_comment(
            case_id,
            author_id,
            body,
            parent_comment_id=parent_comment_id,
            moderation_status=moderation_status,
            screen=False,
            conn=db,
        )
        assert result == "ok", result
        db.commit()
        return comment_id

    return _make
