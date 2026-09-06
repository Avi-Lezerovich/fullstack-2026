# -*- coding: utf-8 -*-
"""`datetime.utcnow()` appears nowhere, and app/clock.py says a test bans it.

    def now_utc() -> _dt.datetime:
        \"\"\"Current UTC as a naive datetime, matching how the columns are stored.

        `datetime.utcnow()` is deprecated and is banned across this codebase by
        tests/unit/test_no_deprecated_utcnow.py.
        \"\"\"

That file did not exist. This is it, and the ban is worth more than tidiness on
two counts.

**It is deprecated and will be removed.** `pytest.ini` turns every
DeprecationWarning raised from `app.*` or `worker.*` into an error, so a call
would fail the suite anyway - but only on the line that actually ran it, which
for a rarely-taken branch could be much later than the commit that introduced
it. Reading the source catches it at once.

**It is a naive datetime that claims to be UTC and is not tagged as such**,
which is exactly the value this schema stores everywhere. So the wrong call
produces a value of the right shape and the right meaning today, and would keep
doing so - the failure mode is not a bug, it is a warning that becomes a
crash on a future Python.

The real answer, and the reason `now_utc` exists at all, is that Python's clock
is never the basis of a scheduling decision here. Deadlines are written with
`UTC_TIMESTAMP()` and compared against `UTC_TIMESTAMP()`, so the web process
and the worker cannot disagree no matter how their container clocks drift.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_SERVER = Path(__file__).resolve().parents[2]

PYTHON_FILES = [
    *sorted((_SERVER / "app").rglob("*.py")),
    *sorted((_SERVER / "worker").rglob("*.py")),
]

# `utcnow` and `utcfromtimestamp` were deprecated together in 3.12.
BANNED_ATTRIBUTES = {"utcnow", "utcfromtimestamp"}


@pytest.mark.parametrize(
    "path", PYTHON_FILES, ids=lambda p: str(p.relative_to(_SERVER)).replace("\\", "/")
)
def test_no_module_calls_a_deprecated_datetime_constructor(path):
    """Parsed rather than grepped, so a comment mentioning it is not a failure.

    Which matters here specifically: `clock.py`'s own docstring names the
    function it is banning, and a substring search would fail on the
    documentation of the rule.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))

    called = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }

    assert not (called & BANNED_ATTRIBUTES), path


def test_now_utc_returns_a_naive_datetime_matching_how_the_columns_are_stored():
    """Naive, and deliberately so: every DATETIME here holds naive UTC.

    A timezone-aware value would compare fine in Python and be written to the
    database with an offset it has no column to record.
    """
    from app.clock import now_utc

    stamped = now_utc()

    assert stamped.tzinfo is None


def test_now_utc_is_actually_utc_and_not_local_time():
    """The naivety is the storage convention, not a licence to use local time.

    Compared against the timezone-aware answer rather than against a constant,
    so this holds wherever the suite runs.
    """
    import datetime as dt

    from app.clock import now_utc

    difference = abs((now_utc() - dt.datetime.now(dt.UTC).replace(tzinfo=None)).total_seconds())

    assert difference < 5


def test_python_never_computes_a_deadline_only_an_offset():
    """The one clock is MySQL's, and clock.py only ever returns minutes.

    Every scheduling function here answers with an int that goes into a
    `DATE_ADD(..., INTERVAL %s MINUTE)`, so the web process and the worker
    cannot disagree about when a phase ends however their container clocks
    drift.
    """
    from app import clock

    assert isinstance(clock.witness_deadline_offset(), int)
    assert isinstance(clock.verdict_deadline_offset(), int)
    assert isinstance(clock.closing_deadline_offset(), int)

    start, end = clock.deliberation_window()
    assert isinstance(start, int) and isinstance(end, int)
    assert start < end


def test_the_trial_calendar_scales_with_one_setting(monkeypatch):
    """PHASE_MINUTES is what makes a seven-day lifecycle observable in a browser.

    Read per call, so changing it needs no restart - and so the whole calendar
    stays in proportion rather than each phase being configured separately.
    """
    from app import clock

    monkeypatch.setenv("PHASE_MINUTES", "1440")
    assert clock.witness_deadline_offset() == 2 * 1440
    assert clock.closing_deadline_offset() == 7 * 1440

    monkeypatch.setenv("PHASE_MINUTES", "2")
    assert clock.witness_deadline_offset() == 4
    assert clock.closing_deadline_offset() == 14
