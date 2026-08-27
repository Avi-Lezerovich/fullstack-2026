"""Notifications: a REST view, and a live stream over the same data.

The stream is the interesting part. Notifications are created by the **worker**,
in a different container, while the stream runs in a **web** process. They share
nothing but MySQL - so rather than introduce a broker, the endpoint is a cursor
over the monotonically increasing `notifications.id`.

That means a notification written by any process reaches every connected
browser with no coordination at all, nothing is lost across a restart (the
cursor is a durable row id), and it works unchanged across any number of
gunicorn workers.

The REST endpoints came first and are not a fallback afterthought: the bell
works on polling alone, and `useNotificationStream` degrades to it silently.
"""

from __future__ import annotations

import json
import threading
import time

from flask import Blueprint, Response, g, jsonify, request

from .. import security
from ..config import get_settings
from ..db import connect
from ..errors import fail
from ..services import notifications_service
from ..validation import positive_int

bp = Blueprint("notifications", __name__)

# Long-lived responses occupy a worker thread each, so their number is capped.
#
# The counter is per PROCESS, not per deployment: with N gunicorn workers the
# real ceiling is N * SSE_MAX_STREAMS. That is the right shape anyway, since
# what is being protected is one process's thread pool.
_open_streams = 0
_streams_lock = threading.Lock()


@bp.get("/notifications")
@security.require_auth
def list_notifications():
    """Newest first for the dropdown, or everything after `since` for polling.

    One endpoint serves both the initial render and the polling fallback, so
    the two cannot drift apart.
    """
    since = request.args.get("since", type=int)
    limit = positive_int(request.args.get("limit"), 30, maximum=100)

    if since is not None:
        items = notifications_service.list_since(g.user_id, since, limit=limit)
    else:
        unread_only = request.args.get("unread") == "1"
        items = notifications_service.list_recent(g.user_id, limit=limit, unread_only=unread_only)

    return jsonify(
        {
            "notifications": items,
            "unread_count": notifications_service.unread_count(g.user_id),
            "latest_id": notifications_service.latest_id(g.user_id),
        }
    ), 200


@bp.post("/notifications/read")
@security.require_auth
def mark_read():
    """Mark specific ids, or everything when none are given.

    The service always scopes by user_id, so passing somebody else's ids marks
    nothing rather than touching their state.
    """
    data = request.get_json(silent=True) or {}
    ids = data.get("ids")
    if ids is not None and not isinstance(ids, list):
        return fail("invalid", "רשימת המזהים אינה תקינה.")

    clean_ids = [int(value) for value in ids if str(value).isdigit()] if ids else None
    marked = notifications_service.mark_read(g.user_id, clean_ids)
    return jsonify(
        {"marked": marked, "unread_count": notifications_service.unread_count(g.user_id)}
    ), 200


@bp.get("/notifications/stream")
@security.require_auth
def stream():
    """Server-sent events, as a polled cursor over notifications.id."""
    settings = get_settings()

    # Captured NOW: the request context is gone by the time the generator runs.
    user_id = g.user_id
    start_from = (
        # Set by the browser automatically when EventSource reconnects, so no
        # notification is missed across a dropped connection.
        request.headers.get("Last-Event-ID")
        or request.args.get("since")
        or notifications_service.latest_id(g.user_id)
    )
    try:
        cursor = int(start_from)
    except (TypeError, ValueError):
        cursor = 0

    global _open_streams
    with _streams_lock:
        if _open_streams >= settings.sse_max_streams:
            # fail() already returns (response, status); 503 is the status we
            # want here rather than the 409 "conflict" maps to, so unpack it
            # instead of wrapping the pair in another tuple - Flask cannot read
            # a nested tuple and answers 500.
            body, _status = fail("conflict", "יותר מדי חיבורים פתוחים. נסה שוב בעוד רגע.")
            return body, 503
        _open_streams += 1

    # Released exactly once, whatever happens to the response.
    #
    # The decrement used to live in the generator's `finally`, which only runs
    # if the generator was actually started - so a response the server never
    # iterated (a client that vanished between headers and body) leaked a slot
    # permanently, and the cap tightened for the life of the process.
    # `call_on_close` fires either way.
    released = threading.Event()

    def release():
        global _open_streams
        if released.is_set():
            return
        released.set()
        with _streams_lock:
            _open_streams -= 1

    def events():
        last_id = cursor
        deadline = time.monotonic() + settings.sse_max_seconds
        try:
            yield ": connected\n\n"
            while time.monotonic() < deadline:
                # A connection is opened and closed PER POLL, never held for
                # the stream's lifetime - otherwise a handful of idle browser
                # tabs would exhaust MySQL's max_connections.
                db = connect()
                try:
                    rows = notifications_service.list_since(user_id, last_id, limit=50, conn=db)
                finally:
                    db.close()

                for row in rows:
                    last_id = row["id"]
                    payload = json.dumps(row, ensure_ascii=False)
                    yield f"id: {last_id}\nevent: notification\ndata: {payload}\n\n"

                if not rows:
                    # A comment frame keeps proxies and load balancers from
                    # deciding an idle connection is dead.
                    yield ": keepalive\n\n"

                time.sleep(settings.sse_poll_seconds)
        finally:
            release()

    response = Response(
        events(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            # Tells nginx and friends not to buffer, which would defeat the
            # entire point by delivering everything at once when we finish.
            "X-Accel-Buffering": "no",
        },
    )
    response.call_on_close(release)
    return response
