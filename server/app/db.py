"""Database access: connections and a very thin query helper.

Two rules hold everywhere below the service layer:

1. **Placeholders are MySQL's own `%s`.** There is no `?` translation layer.
   The previous generation of this project had one, and it was exactly what
   made running the test suite against SQLite look reasonable - which in turn
   meant the tests never exercised the dialect the application actually speaks.

2. **`Db` is a convenience, not an abstraction.** It hands parameters straight
   to PyMySQL and returns plain dicts. It exists only so that services can say
   what they mean in one line instead of five lines of cursor bookkeeping.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

import pymysql
from pymysql.cursors import DictCursor

from .config import get_settings

log = logging.getLogger(__name__)

Params = Sequence[Any] | dict[str, Any]


@dataclass(frozen=True)
class ExecResult:
    """What a write statement did.

    `rowcount` is load-bearing throughout the trial engine: every state
    transition is a conditional UPDATE guarded on the status it expects to
    find, and a rowcount of 0 means another worker got there first.
    """

    rowcount: int
    lastrowid: int


class Db:
    """A PyMySQL connection with the cursor boilerplate folded away."""

    def __init__(self, raw: pymysql.connections.Connection) -> None:
        self._raw = raw

    # --- reads --------------------------------------------------------------

    def query_all(self, sql: str, params: Params = ()) -> list[dict[str, Any]]:
        with self._raw.cursor() as cur:
            cur.execute(sql, params)
            return list(cur.fetchall())

    def query_one(self, sql: str, params: Params = ()) -> dict[str, Any] | None:
        with self._raw.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchone()

    def query_value(self, sql: str, params: Params = (), default: Any = None) -> Any:
        """First column of the first row - for COUNT(*), EXISTS, one id, etc."""
        row = self.query_one(sql, params)
        if not row:
            return default
        return next(iter(row.values()))

    # --- writes -------------------------------------------------------------

    def execute(self, sql: str, params: Params = ()) -> ExecResult:
        with self._raw.cursor() as cur:
            cur.execute(sql, params)
            return ExecResult(rowcount=cur.rowcount, lastrowid=cur.lastrowid)

    def execute_many(self, sql: str, seq: Iterable[Params]) -> ExecResult:
        rows = list(seq)
        if not rows:
            return ExecResult(rowcount=0, lastrowid=0)
        with self._raw.cursor() as cur:
            cur.executemany(sql, rows)
            return ExecResult(rowcount=cur.rowcount, lastrowid=cur.lastrowid)

    # --- transaction control ------------------------------------------------

    def commit(self) -> None:
        self._raw.commit()

    def rollback(self) -> None:
        self._raw.rollback()

    def close(self) -> None:
        try:
            self._raw.close()
        except Exception:  # pragma: no cover - closing a dead socket
            pass

    @property
    def raw(self) -> pymysql.connections.Connection:
        return self._raw


def connect(**overrides: Any) -> Db:
    """Open one connection. Callers are responsible for closing it.

    autocommit is deliberately off: the trial engine's correctness depends on
    grouping "claim the row" and "record the result" into one transaction.
    """
    s = get_settings()
    kwargs: dict[str, Any] = {
        "host": s.db_host,
        "port": s.db_port,
        "user": s.db_user,
        "password": s.db_password,
        "database": s.db_name,
        "charset": "utf8mb4",
        "cursorclass": DictCursor,
        "autocommit": False,
    }
    kwargs.update(overrides)
    return Db(pymysql.connect(**kwargs))


def get_db(**overrides: Any) -> Db:
    """connect(), but tolerant of a MySQL container that is still booting."""
    attempts = int(overrides.pop("attempts", 1))
    delay = float(overrides.pop("delay", 2.0))
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            return connect(**overrides)
        except pymysql.err.OperationalError as exc:  # pragma: no cover - boot race
            last = exc
            if attempt < attempts - 1:
                log.warning("database not ready (%s), retrying in %.1fs", exc, delay)
                time.sleep(delay)
    raise last  # type: ignore[misc]  # pragma: no cover


def wait_for_db(attempts: int = 30, delay: float = 2.0) -> Db:  # pragma: no cover
    """Used by the long-lived processes (worker, seed) at start-up."""
    return get_db(attempts=attempts, delay=delay)


class _OwnedConnection:
    """Context manager implementing the `conn=None` convention.

    Every service function takes an optional `conn`. When one is supplied the
    caller owns the transaction - the service must not commit or close it, so
    a route or a worker task can compose several service calls atomically.
    When none is supplied the service opens its own, commits on success and
    always closes.

        with owned(conn) as db:
            db.execute(...)
            db.commit_if_owned()
    """

    def __init__(self, conn: Db | None) -> None:
        self._owned = conn is None
        self.db = conn if conn is not None else connect()

    def __enter__(self) -> "_OwnedConnection":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        if self._owned:
            if exc_type is not None:
                self.db.rollback()
            self.db.close()
        return False

    @property
    def owned(self) -> bool:
        return self._owned

    def commit_if_owned(self) -> None:
        if self._owned:
            self.db.commit()

    # Delegate the query surface so callers can use the wrapper directly.
    def query_all(self, sql: str, params: Params = ()) -> list[dict[str, Any]]:
        return self.db.query_all(sql, params)

    def query_one(self, sql: str, params: Params = ()) -> dict[str, Any] | None:
        return self.db.query_one(sql, params)

    def query_value(self, sql: str, params: Params = (), default: Any = None) -> Any:
        return self.db.query_value(sql, params, default)

    def execute(self, sql: str, params: Params = ()) -> ExecResult:
        return self.db.execute(sql, params)

    def execute_many(self, sql: str, seq: Iterable[Params]) -> ExecResult:
        return self.db.execute_many(sql, seq)


def owned(conn: Db | None) -> _OwnedConnection:
    return _OwnedConnection(conn)
