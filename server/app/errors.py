"""Service result codes -> HTTP.

Services never import Flask and never raise for ordinary business outcomes.
They return a short string - "ok", "forbidden", "not_found" - and the
blueprint turns it into a status code here. That keeps the rule ("only the
author may withdraw a filing") in the service where it can be unit-tested, and
keeps the routes down to parse / authorise / call / respond.

User-facing text is Hebrew, matching the UI.
"""

from __future__ import annotations

from typing import Any

from flask import jsonify

OK = "ok"
CREATED = "created"
INVALID = "invalid"
UNAUTHORIZED = "unauthorized"
FORBIDDEN = "forbidden"
NOT_FOUND = "not_found"
CONFLICT = "conflict"
CLOSED = "closed"
REJECTED = "rejected"
ALREADY_DONE = "already_done"

RESULT_STATUS: dict[str, int] = {
    OK: 200,
    CREATED: 201,
    ALREADY_DONE: 200,
    INVALID: 400,
    UNAUTHORIZED: 401,
    FORBIDDEN: 403,
    NOT_FOUND: 404,
    CONFLICT: 409,
    # A trial action attempted in the wrong phase. 409 rather than 403: the
    # caller had the right, just not any more.
    CLOSED: 409,
    # Blocked by content moderation. 422 rather than 400: the request was
    # well-formed, we simply refuse to publish it.
    REJECTED: 422,
}

DEFAULT_MESSAGES: dict[str, str] = {
    INVALID: "הבקשה אינה תקינה.",
    UNAUTHORIZED: "נדרשת התחברות.",
    FORBIDDEN: "אין לך הרשאה לבצע את הפעולה הזו.",
    NOT_FOUND: "הפריט המבוקש לא נמצא.",
    CONFLICT: "הפעולה כבר בוצעה.",
    CLOSED: "לא ניתן לבצע את הפעולה בשלב הנוכחי של המשפט.",
    REJECTED: "התוכן נחסם על ידי מנגנון סינון התוכן.",
}


def status_for(result: str) -> int:
    return RESULT_STATUS.get(result, 400)


def fail(result: str, message: str | None = None, **extra: Any):
    """Build an error response for a service result code."""
    body: dict[str, Any] = {
        "error": message or DEFAULT_MESSAGES.get(result, "אירעה שגיאה."),
        "code": result,
    }
    body.update(extra)
    return jsonify(body), status_for(result)


def ok(payload: Any = None, status: int = 200):
    return jsonify(payload if payload is not None else {"ok": True}), status
