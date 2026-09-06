# -*- coding: utf-8 -*-
"""The service layer imports no Flask, and app/services/__init__.py says so.

That docstring has said "This is enforced by tests/unit/test_layering.py" since
the layer was written. The file did not exist. This is it.

The rule matters because the worker is a **separate process** with no request
context at all. A service that reached for `flask.g` or `request` would work
perfectly through the API and raise `RuntimeError: Working outside of request
context` the first time a bot touched it - at three in the morning, inside a
`safe()` that swallows the traceback into a log line.

It is checked by reading the source rather than by importing, so a lazy import
inside a function is caught too. `worker/loop.py` and the tasks it calls are
held to the same rule for the same reason, from the other direction: they are
the code that would do the crashing.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_SERVER = Path(__file__).resolve().parents[2]

# The layers that must be able to run with no request in flight.
REQUEST_FREE = [
    *sorted((_SERVER / "app" / "services").glob("*.py")),
    *sorted((_SERVER / "worker").glob("*.py")),
]

# `app.errors` builds a jsonify() response, so it is Flask by construction and
# belongs to the API layer even though it lives beside the services.
FORBIDDEN_ROOTS = {"flask", "flask_cors", "werkzeug"}


def _imported_roots(path: Path) -> set[str]:
    """Every top-level module this file imports, including inside functions."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    return roots


@pytest.mark.parametrize("path", REQUEST_FREE, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_nothing_below_the_api_layer_imports_flask(path):
    """A service that reads `g` works through the API and dies in the worker.

    Which is the worst shape a bug can have here: it passes every test that
    goes through a route, and fails only in the process that has no route.
    """
    assert not (_imported_roots(path) & FORBIDDEN_ROOTS), path


@pytest.mark.parametrize("path", REQUEST_FREE, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_nothing_below_the_api_layer_imports_the_error_helpers(path):
    """`app.errors` returns a jsonify() pair, so it is the API layer.

    Services return short result codes ("ok", "forbidden") and let the
    blueprint map them to a status - which is what keeps the rule in the
    service, where it can be unit-tested, and the routes down to four lines.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert (node.module or "") != "errors", path
            assert not (node.module or "").endswith(".errors"), path


# The one blueprint allowed to hold SQL, and the reason is its whole purpose:
# /api/health exists to report whether THIS process can reach the database.
# Routing that through a service would prove that the service works, which is
# a different claim - and there is no business rule in `SELECT 1` to test.
SQL_IS_THE_POINT = {"health.py"}


def test_no_blueprint_but_health_writes_its_own_sql():
    """SQL belongs in app/services - the other half of the layering rule.

    A route running its own query puts a rule somewhere it cannot be tested
    without a request context, which is how the service layer stops being the
    single place visibility is decided.
    """
    offenders = []
    for path in sorted((_SERVER / "app" / "api").glob("*.py")):
        if path.name in SQL_IS_THE_POINT:
            continue
        source = path.read_text(encoding="utf-8")
        for keyword in ("SELECT ", "INSERT INTO", "UPDATE ", "DELETE FROM"):
            if keyword in source:
                offenders.append((path.name, keyword))

    assert offenders == []


def test_the_health_exception_stays_a_liveness_probe_and_nothing_more():
    """Pinned so the exemption cannot quietly become a second service layer.

    It may ask whether the connection works and read the worker's own tick
    row - which no service owns, because the worker writes it directly. Any
    write, or a read of a domain table, belongs in app/services.
    """
    source = (_SERVER / "app" / "api" / "health.py").read_text(encoding="utf-8")

    for keyword in ("INSERT INTO", "UPDATE ", "DELETE FROM"):
        assert keyword not in source

    for table in ("cases", "users", "comments", "reports", "sessions"):
        assert f"FROM {table}" not in source
    assert "FROM worker_state" in source


def test_create_app_touches_no_database():
    """The factory is pure, and app/__init__.py explains what it cost to learn.

    When the previous version bootstrapped the schema inside the factory,
    several gunicorn workers raced to create the same tables, deadlocked, and
    had to be papered over with `--preload`. A pure factory can be called
    freely - by any number of workers, and by every test in this suite.
    """
    import app.db

    def refuse(*args, **kwargs):
        raise AssertionError("create_app() opened a database connection")

    original_connect, original_get = app.db.connect, app.db.get_db
    app.db.connect, app.db.get_db = refuse, refuse
    try:
        from app import create_app

        assert create_app() is not None
    finally:
        app.db.connect, app.db.get_db = original_connect, original_get
