"""Locating and executing database/init.sql.

The test suite builds its schema by running this exact file against a real
MySQL 8 server, so the tests exercise the same enums, foreign-key cascades and
`ON DUPLICATE KEY` behaviour the application depends on.

That is only sound while init.sql stays free of `DELIMITER` blocks - a simple
statement splitter cannot handle stored procedures or triggers. Rather than
write a full parser we forbid the construct and assert it in a test.
"""

from __future__ import annotations

import os
from pathlib import Path


def _find_schema() -> Path:
    """init.sql lives beside the code in Docker and above it locally."""
    override = os.environ.get("SCHEMA_PATH", "").strip()
    if override:
        return Path(override)

    here = Path(__file__).resolve()
    candidates = [
        here.parents[1] / "database" / "init.sql",  # image layout:  /app/database
        here.parents[2] / "database" / "init.sql",  # repo layout:   <root>/database
        here.parents[3] / "database" / "init.sql",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return candidates[1]


SCHEMA_PATH = _find_schema()


def split_sql_statements(sql: str) -> list[str]:
    """Split on semicolons that are actually statement terminators.

    Aware of single- and double-quoted strings, backtick identifiers, `--` and
    `#` line comments and `/* */` blocks, so a semicolon inside any of them
    does not split a statement.
    """
    statements: list[str] = []
    buf: list[str] = []
    i = 0
    n = len(sql)
    quote: str | None = None

    while i < n:
        ch = sql[i]

        if quote:
            buf.append(ch)
            if ch == "\\" and quote in ("'", '"') and i + 1 < n:
                # Backslash escape inside a string: consume the next char whole.
                buf.append(sql[i + 1])
                i += 2
                continue
            if ch == quote:
                # '' and "" are literal quotes, not a close-then-open.
                if i + 1 < n and sql[i + 1] == quote:
                    buf.append(sql[i + 1])
                    i += 2
                    continue
                quote = None
            i += 1
            continue

        # -- line comment (MySQL requires whitespace after the dashes)
        if ch == "-" and sql.startswith("--", i) and (i + 2 >= n or sql[i + 2] in " \t\r\n"):
            end = sql.find("\n", i)
            i = n if end == -1 else end + 1
            continue

        # # line comment
        if ch == "#":
            end = sql.find("\n", i)
            i = n if end == -1 else end + 1
            continue

        # /* block comment */
        if ch == "/" and sql.startswith("/*", i):
            end = sql.find("*/", i + 2)
            i = n if end == -1 else end + 2
            continue

        if ch in ("'", '"', "`"):
            quote = ch
            buf.append(ch)
            i += 1
            continue

        if ch == ";":
            statement = "".join(buf).strip()
            if statement:
                statements.append(statement)
            buf = []
            i += 1
            continue

        buf.append(ch)
        i += 1

    tail = "".join(buf).strip()
    if tail:
        statements.append(tail)
    return statements


def read_schema_sql() -> str:
    return SCHEMA_PATH.read_text(encoding="utf-8")


def schema_statements() -> list[str]:
    return split_sql_statements(read_schema_sql())


def load_schema(cursor) -> int:
    """Execute every statement in init.sql. Returns how many ran."""
    statements = schema_statements()
    for statement in statements:
        cursor.execute(statement)
    return len(statements)
