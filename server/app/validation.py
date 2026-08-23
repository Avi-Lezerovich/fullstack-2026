"""Request-shape validation.

Deliberately small and boring. Business rules ("only a case party may summon a
witness") belong in the service layer where they can be unit-tested; this
module only answers "is this field a plausible string of the right size".
"""

from __future__ import annotations

import re
from typing import Any

# Good enough to catch typos and obvious nonsense. Real verification of an
# address is done by sending mail to it.
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")

NAME_MIN = 2
NAME_MAX = 80
EMAIL_MAX = 255


def clean(value: Any, max_length: int | None = None) -> str:
    """Coerce to a trimmed string, optionally truncated."""
    if value is None:
        return ""
    text = str(value).strip()
    if max_length is not None:
        text = text[:max_length]
    return text


def is_email(value: str) -> bool:
    return bool(value) and len(value) <= EMAIL_MAX and EMAIL_RE.match(value) is not None


def name_problem(name: str) -> str | None:
    if len(name) < NAME_MIN:
        return f"השם חייב להכיל לפחות {NAME_MIN} תווים."
    if len(name) > NAME_MAX:
        return f"השם יכול להכיל עד {NAME_MAX} תווים."
    return None


def body_of(request_obj) -> dict[str, Any]:
    """The JSON body as a dict, whatever the client sent.

    `silent=True` so a malformed or absent body becomes a 400 from our own
    validation with a Hebrew message, rather than Werkzeug's English 415.
    """
    data = request_obj.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def positive_int(value: Any, default: int, *, maximum: int | None = None) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    if number < 0:
        return default
    if maximum is not None:
        number = min(number, maximum)
    return number
