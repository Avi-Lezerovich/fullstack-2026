# -*- coding: utf-8 -*-
"""database/init.sql stays executable by a plain client, and the tests prove it.

The schema file's header makes a promise about itself:

    "The test suite executes this exact file against its own schema, so the
     tests exercise the real MySQL dialect. That is only possible while this
     file stays free of triggers, stored procedures and DELIMITER blocks - a
     test asserts it."

No such test existed. The claim was true of the intent and false of the
repository: the suite executed a hand-written SQLite approximation of a schema
three renames out of date, and nothing would have noticed the day somebody
added a trigger.

This is that test. It matters because the whole integration layer is built on
splitting this file on semicolons - the one thing a DELIMITER block exists to
break - so the day the promise stops holding, the harness stops building a
schema at all, and it should fail here with a sentence rather than fifty rows
of syntax error.
"""

from __future__ import annotations

import pytest

from tests.conftest import INIT_SQL, statements_in

pytestmark = pytest.mark.integration

# Anything that needs a client-side DELIMITER to load. Checked after comments
# are stripped, because the header names all three in prose.
FORBIDDEN = ("DELIMITER", "CREATE TRIGGER", "CREATE PROCEDURE", "CREATE FUNCTION")


def _uncommented() -> str:
    return "\n".join(statements_in(INIT_SQL.read_text(encoding="utf-8")))


def test_the_schema_declares_no_triggers_procedures_or_delimiters():
    """The property the header promises, checked on code rather than prose.

    Stripping comments first is load-bearing: the header sentence making the
    promise contains all three forbidden words, so a naive substring search
    over the raw file fails on the documentation of the rule it is enforcing.
    """
    body = _uncommented().upper()

    for keyword in FORBIDDEN:
        assert keyword not in body, f"{keyword} in init.sql breaks the test harness"


def test_no_statement_hides_a_semicolon_inside_a_string_literal():
    """Splitting on `;` is only correct while no literal contains one.

    A seeded row with a semicolon in its text would silently cut a statement in
    half, and the resulting error would point at the fragment rather than at
    the cause.
    """
    for statement in statements_in(INIT_SQL.read_text(encoding="utf-8")):
        # An odd number of quotes means the split landed inside a literal.
        assert statement.count("'") % 2 == 0, statement[:120]


def test_every_statement_in_the_file_is_one_the_server_accepted(db):
    """The schema the tests run against is the one the container would build.

    `_schema` already executed this file to create the database; this asserts
    the outcome rather than the mechanism - every table the file declares is
    present, so a statement that silently failed cannot go unnoticed.
    """
    declared = {
        statement.split("IF NOT EXISTS")[1].strip().split("(")[0].strip()
        for statement in statements_in(INIT_SQL.read_text(encoding="utf-8"))
        if "CREATE TABLE" in statement.upper()
    }
    assert len(declared) >= 20

    present = {
        next(iter(row.values())) for row in db.query_all("SHOW TABLES")
    }
    assert declared <= present


def test_the_worker_state_row_the_file_inserts_is_there(db):
    """init.sql's only INSERT, and the scheduler cannot count ticks without it.

    `bump_tick` is an UPDATE, not an upsert - with no row it updates nothing,
    reads back the default 0 forever, and every periodic task ("every fourth
    tick") stops firing.
    """
    assert db.query_value("SELECT COUNT(*) FROM worker_state WHERE name = 'scheduler'") == 1


# --- init.sql and the migrations must describe the same table -----------------
#
# Two files declare `brain_calls`: `database/init.sql`, which a fresh database
# is built from, and `prod/migrations/004-brain-credentials.sql`, which an
# existing one is upgraded by. They are edited by hand, separately, and
# nothing made them agree.
#
# Drift here is invisible in the worst way. The integration suite builds its
# schema from init.sql, so a migration that adds the wrong column type - or
# forgets a column entirely - passes every test in this repository and then
# fails only in production, as a silently swallowed INSERT in `_log_call` and
# an AI dashboard that quietly stops recording anything.


def _brain_calls_columns(db) -> dict[str, str]:
    return {
        row["COLUMN_NAME"]: row["COLUMN_TYPE"]
        for row in db.query_all(
            "SELECT COLUMN_NAME, COLUMN_TYPE FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'brain_calls'"
        )
    }


def test_migration_004_lands_on_the_same_brain_calls_that_init_sql_declares(db):
    """Upgrade a pre-004 table and compare it, column for column, with init.sql.

    The pre-004 shape is spelled out here rather than read from git, so this
    keeps working after the history is squashed - and so the thing being
    upgraded is stated, which is the part a reader needs.
    """
    from tests.conftest import _REPO_ROOT, statements_in

    expected = _brain_calls_columns(db)

    db.execute("DROP TABLE IF EXISTS brain_calls_migration_check")
    db.execute(
        "CREATE TABLE brain_calls_migration_check ("
        "  id INT AUTO_INCREMENT PRIMARY KEY, task VARCHAR(32) NOT NULL,"
        "  provider VARCHAR(16) NOT NULL, backend ENUM('llm','offline') NOT NULL,"
        "  success TINYINT(1) NOT NULL, fallback_reason VARCHAR(300) NULL,"
        "  input_tokens INT NOT NULL DEFAULT 0, output_tokens INT NOT NULL DEFAULT 0,"
        "  cache_read INT NOT NULL DEFAULT 0, cache_write INT NOT NULL DEFAULT 0,"
        "  created_at DATETIME NOT NULL"
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"
    )
    # A row from before the upgrade: the ALTERs have to be applicable to a
    # table with data in it, which is the only kind production has.
    db.execute(
        "INSERT INTO brain_calls_migration_check "
        "(task, provider, backend, success, created_at) "
        "VALUES ('bot_comment','gemini','llm',1,UTC_TIMESTAMP())"
    )

    migration = _REPO_ROOT / "prod" / "migrations" / "004-brain-credentials.sql"
    for statement in statements_in(migration.read_text(encoding="utf-8")):
        if not statement.upper().startswith("ALTER TABLE"):
            continue
        db.execute(statement.replace("brain_calls", "brain_calls_migration_check", 1))

    migrated = {
        row["COLUMN_NAME"]: row["COLUMN_TYPE"]
        for row in db.query_all(
            "SELECT COLUMN_NAME, COLUMN_TYPE FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() "
            "AND TABLE_NAME = 'brain_calls_migration_check'"
        )
    }
    db.execute("DROP TABLE brain_calls_migration_check")
    db.commit()

    assert migrated == expected


def test_a_pre_migration_row_reads_back_under_its_provider(db):
    """`credential` defaults to '' for history, and must not read as a key.

    The dashboard groups on COALESCE(NULLIF(credential,''), provider), so an
    old row appears under 'gemini' beside the new 'api1-gemini' rather than
    being dropped, or worse, charged to a credential that never made it.
    """
    db.execute(
        "INSERT INTO brain_calls (task, provider, backend, success, "
        "input_tokens, output_tokens, cache_read, cache_write, created_at) "
        "VALUES ('bot_comment','gemini','llm',1,0,0,0,0,UTC_TIMESTAMP())"
    )
    db.commit()

    row = db.query_one(
        "SELECT credential, COALESCE(NULLIF(credential,''), provider) AS reads_as "
        "FROM brain_calls ORDER BY id DESC LIMIT 1"
    )
    assert row["credential"] == ""
    assert row["reads_as"] == "gemini"
