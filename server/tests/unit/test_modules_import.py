# -*- coding: utf-8 -*-
"""Every module in the application actually imports.

This exists because of a bug that reached a commit: a constant lost its value
(`RECORD_LIMIT = ` with nothing after the equals sign), which is a SyntaxError
the moment anything loads that module - and nothing did. The 159 tests around
it all exercise pure functions in `brain/` and `services/`, the API blueprints
are only ever imported by `create_app()`, and `create_app()` is only ever called
by a running server. So a file that could not be parsed passed the entire suite.

The web container would have caught it in about a second. CI would not, and
neither would anybody running pytest before pushing.

Importing every module is a crude test and it is exactly the right size for the
failure it catches: syntax errors, circular imports, a module-level statement
that raises, and a route file that references something that no longer exists.
It needs no database and no network, because nothing in this application does
work at import time - `create_app()` is deliberately side-effect free, and this
test quietly pins that too.
"""

from __future__ import annotations

import importlib
import pkgutil

import pytest

PACKAGES = ("app", "worker", "evals")


def _module_names() -> list[str]:
    names: list[str] = []
    for package_name in PACKAGES:
        package = importlib.import_module(package_name)
        names.append(package_name)
        for info in pkgutil.walk_packages(package.__path__, f"{package_name}."):
            names.append(info.name)
    return sorted(names)


@pytest.mark.parametrize("name", _module_names())
def test_module_imports(name):
    importlib.import_module(name)


def test_the_sweep_actually_covers_the_api_routes():
    """A guard on the guard.

    `walk_packages` returns nothing at all for a package it cannot find, and a
    parametrised test over an empty list is a green test that ran zero times.
    The API blueprints are the specific thing this file was written for, so
    their presence is asserted rather than assumed.
    """
    names = _module_names()
    for expected in ("app.api.users", "app.brain.llm", "worker.social_tasks"):
        assert expected in names
