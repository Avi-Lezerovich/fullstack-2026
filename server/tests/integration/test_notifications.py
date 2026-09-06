# -*- coding: utf-8 -*-
"""Notifications, and the live stream that is a cursor rather than a broker.

The design worth testing here is the transport. Notifications are written by
the **worker**, in another container, and read by a **web** process; the two
share nothing but MySQL. Rather than add a message broker, the stream is a
polled cursor over the monotonically increasing `notifications.id` - which
means a row written by any process reaches every connected browser with no
coordination, survives a restart because the cursor is a durable row id, and
works unchanged across any number of gunicorn workers.

Two consequences are asserted below and neither is obvious:

* `list_since` serves **both** transports, so SSE and the polling fallback
  cannot drift apart. `useNotificationStream` degrades from one to the other
  silently, and it can only do that because the payloads are identical.
* a fresh stream starts at `latest_id`, not at zero. Starting at zero would
  replay the user's entire history on every reconnect, and every row would
  arrive looking new.

The stream tests run under conftest's shrunk `SSE_MAX_SECONDS`, so a "long
lived" response finishes in a fraction of a second.
"""

from __future__ import annotations

import json

import pytest

from app.services import notifications_service as notifications

pytestmark = pytest.mark.integration


@pytest.fixture
def reader(make_user):
    return make_user("הקוראת", "reader@lolsuit.test")


@pytest.fixture
def actor(make_user):
    return make_user("השחקן", "actor@lolsuit.test")


def _events(response) -> list[dict]:
    """Parse an SSE body into the notifications it carried."""
    payloads = []
    for block in response.get_data(as_text=True).split("\n\n"):
        for line in block.splitlines():
            if line.startswith("data: "):
                payloads.append(json.loads(line[len("data: ") :]))
    return payloads


# --- writing ----------------------------------------------------------------


def test_a_notification_records_who_did_what_on_which_case(db, reader, actor, make_case):
    case_id = make_case(actor["id"])

    notification_id = notifications.notify(
        reader["id"], "like", case_id=case_id, actor_user_id=actor["id"],
        payload={"case_title": "תביעה"}, conn=db,
    )
    db.commit()

    row = notifications.list_recent(reader["id"], conn=db)[0]
    assert row["id"] == notification_id
    assert row["type"] == "like"
    assert row["case_id"] == case_id
    assert row["actor"] == {"id": actor["id"], "name": "השחקן"}
    assert row["payload"] == {"case_title": "תביעה"}
    assert row["is_read"] is False


def test_nobody_is_notified_about_their_own_action(db, actor):
    """Liking your own filing should not ping you.

    Skipped here rather than guarded at every call site - `toggle_like` passes
    the case's author unconditionally, and so does every other caller.
    """
    assert notifications.notify(actor["id"], "like", actor_user_id=actor["id"], conn=db) is None
    db.commit()

    assert db.query_value("SELECT COUNT(*) FROM notifications") == 0


def test_a_notification_with_no_recipient_is_skipped_rather_than_failing(db):
    """A case with a free-text defendant has nobody to tell.

    Every caller would otherwise need the same `if defendant_user_id` guard,
    and the one that forgot it would be a foreign-key violation in production.
    """
    assert notifications.notify(None, "verdict", conn=db) is None
    assert notifications.notify(0, "verdict", conn=db) is None
    db.commit()

    assert db.query_value("SELECT COUNT(*) FROM notifications") == 0


def test_a_notification_without_an_actor_shapes_cleanly(db, reader):
    """Moderation and verdicts have no human actor.

    `actor` is null rather than an object of nulls, so the client renders
    "your filing was hidden" without inventing a person who did it.
    """
    notifications.notify(reader["id"], "moderation", payload={"status": "hidden"}, conn=db)
    db.commit()

    row = notifications.list_recent(reader["id"], conn=db)[0]
    assert row["actor"] is None
    assert row["payload"] == {"status": "hidden"}


def test_a_notification_with_no_payload_reads_as_an_empty_object(db, reader):
    """`{}` rather than null, so the client can index it without a guard."""
    notifications.notify(reader["id"], "verdict", conn=db)
    db.commit()

    assert notifications.list_recent(reader["id"], conn=db)[0]["payload"] == {}


# --- reading ----------------------------------------------------------------


def test_the_dropdown_reads_newest_first_and_the_stream_reads_oldest_first(db, reader):
    """Two orders over one table, and each is right for its reader.

    The bell shows what just happened; the stream replays a backlog in the
    order it occurred, so the cursor can only ever move forwards.
    """
    for index in range(3):
        notifications.notify(reader["id"], "like", payload={"n": index}, conn=db)
    db.commit()

    newest_first = notifications.list_recent(reader["id"], conn=db)
    oldest_first = notifications.list_since(reader["id"], 0, conn=db)

    assert [row["payload"]["n"] for row in newest_first] == [2, 1, 0]
    assert [row["payload"]["n"] for row in oldest_first] == [0, 1, 2]


def test_the_bell_can_ask_for_unread_only(db, reader):
    first = notifications.notify(reader["id"], "like", conn=db)
    notifications.notify(reader["id"], "comment", conn=db)
    db.commit()
    notifications.mark_read(reader["id"], [first], conn=db)
    db.commit()

    assert len(notifications.list_recent(reader["id"], conn=db)) == 2
    unread = notifications.list_recent(reader["id"], unread_only=True, conn=db)
    assert [row["type"] for row in unread] == ["comment"]


def test_nobody_sees_anybody_elses_notifications(db, reader, actor):
    """`user_id` is in the WHERE clause of every read in this module."""
    notifications.notify(actor["id"], "like", conn=db)
    db.commit()

    assert notifications.list_recent(reader["id"], conn=db) == []
    assert notifications.list_since(reader["id"], 0, conn=db) == []
    assert notifications.unread_count(reader["id"], conn=db) == 0
    assert notifications.latest_id(reader["id"], conn=db) == 0


def test_the_cursor_starts_at_the_latest_id_so_a_new_stream_replays_nothing(db, reader):
    """Otherwise every reconnect would deliver the whole history as news.

    Zero for a user with none, which is also the right starting cursor.
    """
    assert notifications.latest_id(reader["id"], conn=db) == 0

    last = None
    for _ in range(3):
        last = notifications.notify(reader["id"], "like", conn=db)
    db.commit()

    assert notifications.latest_id(reader["id"], conn=db) == last
    assert notifications.list_since(reader["id"], last, conn=db) == []


# --- marking read -----------------------------------------------------------


def test_marking_specific_ids_leaves_the_rest_alone(db, reader):
    first = notifications.notify(reader["id"], "like", conn=db)
    notifications.notify(reader["id"], "comment", conn=db)
    db.commit()

    assert notifications.mark_read(reader["id"], [first], conn=db) == 1
    db.commit()

    assert notifications.unread_count(reader["id"], conn=db) == 1


def test_marking_with_no_ids_clears_everything(db, reader):
    for _ in range(3):
        notifications.notify(reader["id"], "like", conn=db)
    db.commit()

    assert notifications.mark_read(reader["id"], conn=db) == 3
    db.commit()

    assert notifications.unread_count(reader["id"], conn=db) == 0
    # Already read, so nothing to do the second time.
    assert notifications.mark_read(reader["id"], conn=db) == 0


def test_passing_somebody_elses_ids_marks_nothing(db, reader, actor):
    """`user_id` is always in the WHERE clause, so this is not even a leak -
    it simply matches no rows."""
    theirs = notifications.notify(actor["id"], "like", conn=db)
    db.commit()

    assert notifications.mark_read(reader["id"], [theirs], conn=db) == 0
    db.commit()

    assert notifications.unread_count(actor["id"], conn=db) == 1


# --- the REST endpoints -----------------------------------------------------


def test_the_endpoint_serves_the_dropdown_with_its_counters(client, db, reader, signed_in):
    for _ in range(2):
        notifications.notify(reader["id"], "like", conn=db)
    db.commit()
    signed_in(reader)

    payload = client.get("/api/notifications").get_json()

    assert len(payload["notifications"]) == 2
    assert payload["unread_count"] == 2
    assert payload["latest_id"] == notifications.latest_id(reader["id"], conn=db)


def test_the_same_endpoint_serves_the_polling_fallback(client, db, reader, signed_in):
    """`?since=` switches it from "newest first" to "everything after".

    One endpoint for both so the initial render and the poll cannot drift -
    which is what lets `useNotificationStream` fall back silently.
    """
    first = notifications.notify(reader["id"], "like", conn=db)
    notifications.notify(reader["id"], "comment", conn=db)
    db.commit()
    signed_in(reader)

    payload = client.get(f"/api/notifications?since={first}").get_json()

    assert [row["type"] for row in payload["notifications"]] == ["comment"]


def test_the_dropdown_can_be_filtered_and_limited(client, db, reader, signed_in):
    for _ in range(5):
        notifications.notify(reader["id"], "like", conn=db)
    db.commit()
    signed_in(reader)

    assert len(client.get("/api/notifications?limit=2").get_json()["notifications"]) == 2
    assert len(client.get("/api/notifications?unread=1").get_json()["notifications"]) == 5

    client.post("/api/notifications/read", json={})
    assert client.get("/api/notifications?unread=1").get_json()["notifications"] == []


def test_marking_read_through_the_endpoint_returns_the_new_count(
    client, db, reader, signed_in
):
    first = notifications.notify(reader["id"], "like", conn=db)
    notifications.notify(reader["id"], "comment", conn=db)
    db.commit()
    signed_in(reader)

    payload = client.post("/api/notifications/read", json={"ids": [first]}).get_json()

    assert payload == {"marked": 1, "unread_count": 1}

    assert client.post("/api/notifications/read", json={}).get_json()["unread_count"] == 0


def test_a_malformed_ids_list_is_refused_and_junk_entries_are_dropped(
    client, db, reader, signed_in
):
    """A list is required, but its contents are filtered rather than rejected.

    A client sending one bad id among twenty good ones should still get the
    nineteen marked.
    """
    first = notifications.notify(reader["id"], "like", conn=db)
    db.commit()
    signed_in(reader)

    assert client.post("/api/notifications/read", json={"ids": "all"}).status_code == 400

    payload = client.post(
        "/api/notifications/read", json={"ids": [first, "nonsense", None]}
    ).get_json()
    assert payload["marked"] == 1


def test_the_notification_endpoints_need_a_session(client):
    assert client.get("/api/notifications").status_code == 401
    assert client.post("/api/notifications/read", json={}).status_code == 401
    assert client.get("/api/notifications/stream").status_code == 401


# --- the stream -------------------------------------------------------------


def test_the_stream_announces_itself_and_declares_it_must_not_be_buffered(
    client, reader, signed_in
):
    """`X-Accel-Buffering: no` is what stops nginx defeating the whole point.

    Buffered, the proxy would hold every frame and deliver them all at once
    when the response finished - which for a stream is exactly never.
    """
    signed_in(reader)

    response = client.get("/api/notifications/stream")

    assert response.status_code == 200
    assert response.mimetype == "text/event-stream"
    assert response.headers["X-Accel-Buffering"] == "no"
    assert "no-cache" in response.headers["Cache-Control"]

    body = response.get_data(as_text=True)
    assert body.startswith(": connected")
    # An idle stream still writes, so a proxy does not decide it has died.
    assert ": keepalive" in body


def test_the_stream_delivers_rows_written_after_it_opened(client, db, reader, signed_in):
    """Which is the whole mechanism: another process wrote these.

    Nothing coordinated the two; the reader simply asked for ids greater than
    the one it had.
    """
    signed_in(reader)
    notifications.notify(reader["id"], "verdict", payload={"n": 1}, conn=db)
    notifications.notify(reader["id"], "like", payload={"n": 2}, conn=db)
    db.commit()

    delivered = _events(client.get("/api/notifications/stream?since=0"))

    assert [row["payload"]["n"] for row in delivered] == [1, 2]
    assert [row["type"] for row in delivered] == ["verdict", "like"]


def test_a_fresh_stream_does_not_replay_the_backlog(client, db, reader, signed_in):
    """No `since`, so it starts at `latest_id`.

    Starting at zero would deliver everything the user has ever been sent, all
    of it looking new, on every reconnect.
    """
    for _ in range(3):
        notifications.notify(reader["id"], "like", conn=db)
    db.commit()
    signed_in(reader)

    assert _events(client.get("/api/notifications/stream")) == []


def test_a_reconnecting_browser_resumes_from_its_last_event_id(
    client, db, reader, signed_in
):
    """`Last-Event-ID` is set by the browser automatically on reconnect.

    Honouring it is what makes a dropped connection lossless - the frames each
    carry `id:`, so the browser always knows where it got to.
    """
    first = notifications.notify(reader["id"], "like", payload={"n": 1}, conn=db)
    notifications.notify(reader["id"], "comment", payload={"n": 2}, conn=db)
    db.commit()
    signed_in(reader)

    response = client.get(
        "/api/notifications/stream", headers={"Last-Event-ID": str(first)}
    )

    assert [row["payload"]["n"] for row in _events(response)] == [2]
    assert f"id: {first + 1}" in response.get_data(as_text=True)


def test_a_meaningless_cursor_falls_back_to_the_beginning(client, db, reader, signed_in):
    """Rather than 500 on an int() a client is free to get wrong."""
    notifications.notify(reader["id"], "like", conn=db)
    db.commit()
    signed_in(reader)

    assert len(_events(client.get("/api/notifications/stream?since=abc"))) == 1


def test_a_stream_only_ever_carries_its_own_users_rows(client, db, reader, actor, signed_in):
    """`user_id` is captured from the request context before the generator runs.

    It has to be: by the time the generator is iterated the request context is
    gone, and reading `g` there would be an error - or worse, somebody else's.
    """
    notifications.notify(actor["id"], "like", conn=db)
    db.commit()
    signed_in(reader)

    assert _events(client.get("/api/notifications/stream?since=0")) == []


def test_too_many_open_streams_is_a_503_rather_than_a_queue(client, reader, signed_in, monkeypatch):
    """Each stream occupies a worker thread, so the number is capped.

    503 and not 409: the caller should retry shortly, which is what the status
    means - `fail("conflict")` is unpacked precisely so the code and the status
    can disagree here.
    """
    monkeypatch.setenv("SSE_MAX_STREAMS", "0")
    signed_in(reader)

    response = client.get("/api/notifications/stream")

    assert response.status_code == 503
    assert response.get_json()["code"] == "conflict"


def test_a_finished_stream_gives_its_slot_back(client, reader, signed_in, monkeypatch):
    """Regression: the decrement used to live in the generator's `finally`.

    A response the server never iterated - a client that vanished between the
    headers and the body - leaked a slot permanently, and the cap tightened
    for the life of the process. `call_on_close` fires either way.
    """
    monkeypatch.setenv("SSE_MAX_STREAMS", "1")
    signed_in(reader)

    for _ in range(3):
        response = client.get("/api/notifications/stream")
        assert response.status_code == 200
        response.close()


# --- the notifications the rest of the app actually sends -------------------


def test_the_things_that_happen_to_you_all_arrive_as_notifications(
    db, reader, actor, make_case, make_comment
):
    """One test that the wiring exists, across the four sources.

    Each is covered in its own file; what this pins is that they all land in
    the same table with the right `type`, which is what the bell renders from.
    """
    from app.services import likes_service, messages_service

    case_id = make_case(reader["id"])
    likes_service.toggle_like(case_id, actor["id"], conn=db)
    make_comment(case_id, actor["id"])
    messages_service.send_message(actor["id"], reader["id"], "שלום", conn=db)
    db.commit()

    arrived = {row["type"] for row in notifications.list_recent(reader["id"], conn=db)}

    assert {"like", "comment", "message"} <= arrived
