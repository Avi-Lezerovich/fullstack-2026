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
