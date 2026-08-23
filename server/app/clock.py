"""Time, and the one place trial-phase arithmetic is allowed to happen.

There is exactly **one clock**: MySQL's. Every deadline is written with
`UTC_TIMESTAMP()` and compared against `UTC_TIMESTAMP()`, so the web process
and the worker can never disagree about whether a phase has ended, no matter
how their container clocks drift.

Python's job is only to compute *offsets* in minutes. `now_utc()` exists for
stamping values that are not deadlines (and for tests); it is never the basis
of a scheduling decision.
"""

from __future__ import annotations

import datetime as _dt

from .config import get_settings

# The trial calendar, in "days". PHASE_MINUTES decides how long a day is.
#
#   filed ---- 0 ----> witness phase ---- 2 ----> jury deliberation
#                                                        |
#                                          jurors speak between 2 and 5
#                                                        |
#                                      6 ----> verdict ---- 7 ----> closed
DAY_WITNESS_END = 2
DAY_DELIBERATION_START = 2
DAY_DELIBERATION_END = 5
DAY_VERDICT = 6
DAY_CLOSED = 7


def now_utc() -> _dt.datetime:
    """Current UTC as a naive datetime, matching how the columns are stored.

    `datetime.utcnow()` is deprecated and is banned across this codebase by
    tests/unit/test_no_deprecated_utcnow.py.
    """
    return _dt.datetime.now(_dt.UTC).replace(tzinfo=None)


def phase_minutes() -> int:
    return get_settings().phase_minutes


def phase_offset(day: float) -> int:
    """How many minutes past filing a given trial 'day' falls.

    With PHASE_MINUTES=1440 a day is a day. With PHASE_MINUTES=2 the whole
    seven-day lifecycle takes fourteen minutes, which is what makes the trial
    engine observable in a browser.
    """
    return int(round(day * phase_minutes()))


def witness_deadline_offset() -> int:
    return phase_offset(DAY_WITNESS_END)


def verdict_deadline_offset() -> int:
    return phase_offset(DAY_VERDICT)


def closing_deadline_offset() -> int:
    return phase_offset(DAY_CLOSED)


def deliberation_window() -> tuple[int, int]:
    """(start, end) minutes past filing, the span jurors speak within."""
    return phase_offset(DAY_DELIBERATION_START), phase_offset(DAY_DELIBERATION_END)
