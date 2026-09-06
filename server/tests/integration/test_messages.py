# -*- coding: utf-8 -*-
"""Direct messages: one conversation per pair, and nobody else in it.

Two rules carry this module, and both are the kind that a test written against
a fake would confirm rather than check.

**A conversation is keyed on an ordered pair.** MySQL 8 will not let
`user_a_id < user_b_id` be a CHECK constraint (error 3823 again), so the
ordering is enforced in Python by `_ordered` and the UNIQUE index only catches
duplicates that already agree about the order. Get the ordering wrong and
A-to-B and B-to-A become two conversations that each hold half the
correspondence - which is precisely why this is tested by sending in both
directions and asserting there is still one row.

**`is_participant` is the whole access control.** There is no other check
anywhere; the thread, the read-marking and the unread count all route through
it. It answers with a row from `conversations`, so it is tested here against
the real table rather than against a fake that would simply agree.

The third thing worth pinning is `recent_messages` versus `thread` - two
readers over the same rows that take their window from opposite ends, which is
a difference no type signature shows.
"""

from __future__ import annotations

import pytest

from app.services import messages_service as messages

pytestmark = pytest.mark.integration


@pytest.fixture
def alice(make_user):
    return make_user("אליס", "alice@lolsuit.test")


@pytest.fixture
def bob(make_user):
    return make_user("בוב", "bob@lolsuit.test")


@pytest.fixture
def carol(make_user):
    return make_user("קרול", "carol@lolsuit.test")


# --- one conversation per pair ----------------------------------------------


def test_the_pair_is_ordered_so_direction_cannot_split_a_conversation(db, alice, bob):
    """A to B and B to A are one thread, and the row proves it.

    Without `_ordered` the UNIQUE index would happily hold both (alice, bob)
    and (bob, alice), and each person would see only the half they started.
    """
    messages.send_message(alice["id"], bob["id"], "שלום", conn=db)
    messages.send_message(bob["id"], alice["id"], "שלום גם לך", conn=db)
    db.commit()

    assert db.query_value("SELECT COUNT(*) FROM conversations") == 1

    low, high = sorted([alice["id"], bob["id"]])
    row = db.query_one("SELECT user_a_id, user_b_id FROM conversations")
    assert (row["user_a_id"], row["user_b_id"]) == (low, high)


def test_both_users_resolve_the_same_conversation_id(db, alice, bob):
    messages.send_message(alice["id"], bob["id"], "שלום", conn=db)
    db.commit()

    assert messages.find_conversation(alice["id"], bob["id"], conn=db) == messages.find_conversation(
        bob["id"], alice["id"], conn=db
    )


def test_looking_someone_up_creates_nothing(db, alice, bob):
    """Regression: opening a profile used to write an empty thread.

    "Send a message" called the creating version, so walking away without
    typing left a dash-preview conversation in two inboxes forever. A
    conversation now begins when somebody says something.
    """
    assert messages.find_conversation(alice["id"], bob["id"], conn=db) is None
    assert db.query_value("SELECT COUNT(*) FROM conversations") == 0

    assert messages.conversation_for_pair(alice["id"], bob["id"], conn=db) is not None
    db.commit()
    assert db.query_value("SELECT COUNT(*) FROM conversations") == 1


def test_asking_twice_returns_the_existing_conversation(db, alice, bob):
    first = messages.conversation_for_pair(alice["id"], bob["id"], conn=db)
    db.commit()
    second = messages.conversation_for_pair(bob["id"], alice["id"], conn=db)
    db.commit()

    assert first == second
    assert db.query_value("SELECT COUNT(*) FROM conversations") == 1


def test_nobody_can_hold_a_conversation_with_themselves(db, alice):
    """Refused before the insert, because the UNIQUE index would allow it.

    `(alice, alice)` is a perfectly good ordered pair as far as the database is
    concerned, so this rule has nowhere else to live.
    """
    assert messages.find_conversation(alice["id"], alice["id"], conn=db) is None
    assert messages.conversation_for_pair(alice["id"], alice["id"], conn=db) is None
    assert messages.send_message(alice["id"], alice["id"], "שלום לי", conn=db) == ("invalid", None)


# --- sending ----------------------------------------------------------------


def test_sending_stores_the_message_and_moves_the_conversation_to_the_top(db, alice, bob):
    """`last_message_at` is denormalised, so it has to be written here.

    The inbox orders on it; a message that did not update it would arrive and
    leave the thread sitting wherever it already was.
    """
    result, message_id = messages.send_message(alice["id"], bob["id"], "הודעה ראשונה", conn=db)
    db.commit()

    assert result == "ok"
    row = db.query_one("SELECT * FROM messages WHERE id = %s", (message_id,))
    assert row["body"] == "הודעה ראשונה"
    assert row["sender_id"] == alice["id"]
    assert row["read_at"] is None

    assert db.query_value("SELECT last_message_at FROM conversations") is not None


def test_an_empty_or_whitespace_message_is_refused(db, alice, bob):
    for body in ("", "   ", "\n\t "):
        assert messages.send_message(alice["id"], bob["id"], body, conn=db) == ("invalid", None)

    assert db.query_value("SELECT COUNT(*) FROM messages") == 0
    assert db.query_value("SELECT COUNT(*) FROM conversations") == 0


def test_an_overlong_message_is_truncated_rather_than_rejected(db, alice, bob):
    """The words are not the problem, so the excess is simply dropped.

    The column has a limit and the client should not be able to exceed it, but
    refusing outright would lose a long message a user actually wrote.
    """
    result, message_id = messages.send_message(
        alice["id"], bob["id"], "א" * (messages.BODY_MAX_LENGTH + 500), conn=db
    )
    db.commit()

    assert result == "ok"
    stored = db.query_value("SELECT body FROM messages WHERE id = %s", (message_id,))
    assert len(stored) == messages.BODY_MAX_LENGTH


def test_a_banned_or_missing_recipient_cannot_be_messaged(db, alice, make_user):
    """And no conversation is left behind by the attempt."""
    banned = make_user("מושעה", "banned@lolsuit.test", status="banned")

    assert messages.send_message(alice["id"], banned["id"], "שלום", conn=db) == ("not_found", None)
    assert messages.send_message(alice["id"], 999_999, "שלום", conn=db) == ("not_found", None)
    db.commit()

    assert db.query_value("SELECT COUNT(*) FROM conversations") == 0


def test_the_recipient_is_notified_and_the_sender_is_not(db, alice, bob):
    """The notification is what makes the inbox badge appear.

    Notifying the sender too would make every message you send arrive back at
    you as news.
    """
    messages.send_message(alice["id"], bob["id"], "יש לך הודעה", conn=db)
    db.commit()

    assert db.query_value("SELECT COUNT(*) FROM notifications WHERE user_id = %s", (alice["id"],)) == 0
    row = db.query_one("SELECT type, payload FROM notifications WHERE user_id = %s", (bob["id"],))
    assert row["type"] == "message"
    assert "יש לך הודעה" in row["payload"]


# --- reading ----------------------------------------------------------------


def test_a_third_person_cannot_read_a_conversation(db, alice, bob, carol):
    """`is_participant` is the entire access control on this module.

    None rather than an empty list, so the route can answer 404 - an empty
    thread would say "this conversation exists and has no messages", which is
    itself a fact about two other people.
    """
    messages.send_message(alice["id"], bob["id"], "בינינו", conn=db)
    db.commit()
    conversation = messages.find_conversation(alice["id"], bob["id"], conn=db)

    assert messages.is_participant(conversation, carol["id"], conn=db) is False
    assert messages.thread(conversation, carol["id"], conn=db) is None
    assert messages.thread(999_999, alice["id"], conn=db) is None

    assert messages.is_participant(conversation, alice["id"], conn=db) is True
    assert messages.thread(conversation, alice["id"], conn=db) is not None


def test_a_thread_reads_oldest_first_and_marks_whose_line_is_whose(db, alice, bob):
    """`is_mine` is computed per viewer, so the same rows render differently."""
    messages.send_message(alice["id"], bob["id"], "ראשונה", conn=db)
    messages.send_message(bob["id"], alice["id"], "שנייה", conn=db)
    messages.send_message(alice["id"], bob["id"], "שלישית", conn=db)
    db.commit()
    conversation = messages.find_conversation(alice["id"], bob["id"], conn=db)

    seen_by_alice = messages.thread(conversation, alice["id"], conn=db)

    assert [line["body"] for line in seen_by_alice] == ["ראשונה", "שנייה", "שלישית"]
    assert [line["is_mine"] for line in seen_by_alice] == [True, False, True]

    seen_by_bob = messages.thread(conversation, bob["id"], conn=db)
    assert [line["is_mine"] for line in seen_by_bob] == [False, True, False]


def test_recent_messages_takes_the_end_of_a_thread_where_thread_takes_the_start(
    db, alice, bob
):
    """Two readers, two windows, opposite ends - and that is the whole reason
    `recent_messages` is a separate function rather than a flag.

    It exists for a bot about to reply. Handing it the opening of a long
    correspondence and calling it "recent" would have it answer a question
    somebody asked last month.
    """
    for index in range(10):
        messages.send_message(alice["id"], bob["id"], f"הודעה {index}", conn=db)
    db.commit()
    conversation = messages.find_conversation(alice["id"], bob["id"], conn=db)

    beginning = messages.thread(conversation, bob["id"], limit=3, conn=db)
    end = messages.recent_messages(conversation, limit=3, conn=db)

    assert [line["body"] for line in beginning] == ["הודעה 0", "הודעה 1", "הודעה 2"]
    assert [row["body"] for row in end] == ["הודעה 7", "הודעה 8", "הודעה 9"]


# --- unread counts ----------------------------------------------------------


def test_reading_a_thread_marks_the_other_persons_lines_and_never_your_own(
    db, alice, bob
):
    """Marking your own would make `unread_total` count them as read for the
    recipient too, and their badge would clear because *you* opened the thread.
    """
    messages.send_message(alice["id"], bob["id"], "אליס אומרת", conn=db)
    messages.send_message(bob["id"], alice["id"], "בוב עונה", conn=db)
    db.commit()
    conversation = messages.find_conversation(alice["id"], bob["id"], conn=db)

    assert messages.mark_thread_read(conversation, alice["id"], conn=db) == 1
    db.commit()

    rows = db.query_all("SELECT sender_id, read_at FROM messages ORDER BY id")
    read_state = {row["sender_id"]: row["read_at"] is not None for row in rows}
    assert read_state == {alice["id"]: False, bob["id"]: True}


def test_marking_read_twice_changes_nothing_the_second_time(db, alice, bob):
    """`read_at IS NULL` in the WHERE clause, so the timestamp is not rewritten.

    The thread endpoint marks on every open, and a message's read time should
    be when it was first seen.
    """
    messages.send_message(bob["id"], alice["id"], "הודעה", conn=db)
    db.commit()
    conversation = messages.find_conversation(alice["id"], bob["id"], conn=db)

    assert messages.mark_thread_read(conversation, alice["id"], conn=db) == 1
    db.commit()
    assert messages.mark_thread_read(conversation, alice["id"], conn=db) == 0


def test_a_stranger_marking_a_thread_read_does_nothing(db, alice, bob, carol):
    messages.send_message(alice["id"], bob["id"], "בינינו", conn=db)
    db.commit()
    conversation = messages.find_conversation(alice["id"], bob["id"], conn=db)

    assert messages.mark_thread_read(conversation, carol["id"], conn=db) == 0
    db.commit()

    assert db.query_value("SELECT COUNT(*) FROM messages WHERE read_at IS NOT NULL") == 0


def test_the_unread_total_counts_other_peoples_messages_across_conversations(
    db, alice, bob, carol
):
    """One number for the badge, over every thread.

    Counting your own sent messages would make the badge rise every time you
    said anything.
    """
    messages.send_message(bob["id"], alice["id"], "מבוב", conn=db)
    messages.send_message(carol["id"], alice["id"], "מקרול", conn=db)
    messages.send_message(alice["id"], bob["id"], "מאליס", conn=db)
    db.commit()

    assert messages.unread_total(alice["id"], conn=db) == 2
    assert messages.unread_total(bob["id"], conn=db) == 1
    assert messages.unread_total(carol["id"], conn=db) == 0


def test_the_inbox_lists_the_other_person_the_last_line_and_the_unread_count(
    db, alice, bob, carol
):
    """One query for all of it - it used to be 1 + 3N.

    The badge refetches this on every navigation, so the per-conversation round
    trips were paid constantly rather than once.
    """
    messages.send_message(bob["id"], alice["id"], "הודעה מבוב", conn=db)
    messages.send_message(carol["id"], alice["id"], "ראשונה מקרול", conn=db)
    messages.send_message(carol["id"], alice["id"], "אחרונה מקרול", conn=db)
    # `last_message_at` is a DATETIME, so three messages sent inside one second
    # tie and the order between them is unspecified. Pushing Bob's thread into
    # the past is what makes the ordering assertion below about the ORDER BY
    # rather than about how fast the test ran.
    db.execute(
        "UPDATE conversations SET last_message_at = DATE_SUB(UTC_TIMESTAMP(), INTERVAL 1 HOUR) "
        "WHERE user_a_id = %s OR user_b_id = %s",
        (bob["id"], bob["id"]),
    )
    db.commit()

    inbox = messages.list_conversations(alice["id"], conn=db)

    assert len(inbox) == 2
    # Most recent first.
    assert inbox[0]["other"]["id"] == carol["id"]
    assert inbox[0]["other"]["name"] == "קרול"
    assert inbox[0]["last_message"]["body"] == "אחרונה מקרול"
    assert inbox[0]["unread_count"] == 2
    assert inbox[1]["other"]["id"] == bob["id"]
    assert inbox[1]["unread_count"] == 1


def test_a_conversation_with_nothing_said_in_it_still_lists_without_a_last_line(
    db, alice, bob
):
    """`last_message` is null rather than absent, and the row still appears.

    `conversation_for_pair` can be called without a message following it, so
    the shaping has to survive a thread with no messages - which is what the
    `if row["last_body"] is not None` arm is for.
    """
    messages.conversation_for_pair(alice["id"], bob["id"], conn=db)
    db.commit()

    inbox = messages.list_conversations(alice["id"], conn=db)

    assert len(inbox) == 1
    assert inbox[0]["last_message"] is None
    assert inbox[0]["unread_count"] == 0


# --- through the endpoints --------------------------------------------------


def test_the_thread_endpoint_marks_it_read_as_a_side_effect(client, db, alice, bob, signed_in):
    """Opening a conversation is what clears its badge.

    Requiring a separate call would leave the count wrong for as long as the
    client forgot to make it.
    """
    messages.send_message(bob["id"], alice["id"], "שלום", conn=db)
    db.commit()
    conversation = messages.find_conversation(alice["id"], bob["id"], conn=db)

    signed_in(alice)
    assert client.get("/api/conversations").get_json()["unread_total"] == 1

    assert client.get(f"/api/conversations/{conversation}").status_code == 200

    assert client.get("/api/conversations").get_json()["unread_total"] == 0


def test_the_thread_endpoint_answers_404_to_somebody_elses_conversation(
    client, db, alice, bob, carol, signed_in
):
    """404 rather than 403, so it does not confirm the conversation exists."""
    messages.send_message(alice["id"], bob["id"], "בינינו", conn=db)
    db.commit()
    conversation = messages.find_conversation(alice["id"], bob["id"], conn=db)

    signed_in(carol)

    response = client.get(f"/api/conversations/{conversation}")
    assert response.status_code == 404
    assert client.get("/api/conversations/999999").status_code == 404


def test_sending_through_the_endpoint_returns_the_conversation_it_started(
    client, alice, bob, signed_in
):
    """The client needs the id to open the thread its own message just created.

    Without it the composer would have to guess, or refetch the whole inbox to
    find out where the message went.
    """
    signed_in(alice)

    response = client.post(
        "/api/messages", json={"recipient_id": bob["id"], "body": "הודעה ראשונה"}
    )

    assert response.status_code == 201
    payload = response.get_json()
    assert payload["conversation_id"] is not None
    assert client.get(f"/api/conversations/{payload['conversation_id']}").status_code == 200


@pytest.mark.parametrize(
    ("payload", "why"),
    [
        ({"body": "שלום"}, "no recipient"),
        ({"recipient_id": "abc", "body": "שלום"}, "recipient is not a number"),
        ({"recipient_id": 1, "body": "   "}, "empty body"),
    ],
    ids=["no-recipient", "bad-recipient", "empty-body"],
)
def test_a_malformed_send_is_a_400(client, alice, signed_in, payload, why):
    signed_in(alice)

    assert client.post("/api/messages", json=payload).status_code == 400, why


def test_the_endpoint_refuses_to_message_yourself_in_its_own_words(client, alice, signed_in):
    """Checked in the route as well as the service.

    Reaching the service first would surface as a foreign-key violation about
    a conversation, which is an error about a completely different problem.
    """
    signed_in(alice)

    send = client.post("/api/messages", json={"recipient_id": alice["id"], "body": "שלום"})
    lookup = client.get(f"/api/conversations/with/{alice['id']}")

    assert send.status_code == 400
    assert lookup.status_code == 400


def test_looking_up_a_conversation_that_does_not_exist_yet_says_so_without_creating_it(
    client, db, alice, bob, signed_in
):
    """null, plus the recipient to compose against."""
    signed_in(alice)

    response = client.get(f"/api/conversations/with/{bob['id']}")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["conversation_id"] is None
    assert payload["recipient"]["id"] == bob["id"]
    assert "email" not in payload["recipient"]
    assert db.query_value("SELECT COUNT(*) FROM conversations") == 0


def test_looking_up_a_banned_or_missing_person_is_a_404(client, alice, signed_in, make_user):
    banned = make_user("מושעה", "banned@lolsuit.test", status="banned")
    signed_in(alice)

    assert client.get(f"/api/conversations/with/{banned['id']}").status_code == 404
    assert client.get("/api/conversations/with/999999").status_code == 404


def test_every_message_endpoint_needs_a_session(client):
    assert client.get("/api/conversations").status_code == 401
    assert client.get("/api/conversations/1").status_code == 401
    assert client.get("/api/conversations/with/1").status_code == 401
    assert client.post("/api/messages", json={"recipient_id": 1, "body": "x"}).status_code == 401
