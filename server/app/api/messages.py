"""Direct messages."""

from __future__ import annotations

from flask import Blueprint, g, jsonify, request

from .. import security
from ..errors import fail
from ..services import messages_service, users_service
from ..validation import body_of, clean, positive_int

bp = Blueprint("messages", __name__)


@bp.get("/conversations")
@security.require_auth
def list_conversations():
    return jsonify(
        {
            "conversations": messages_service.list_conversations(g.user_id),
            "unread_total": messages_service.unread_total(g.user_id),
        }
    ), 200


@bp.get("/conversations/<int:conversation_id>")
@security.require_auth
def get_thread(conversation_id: int):
    limit = positive_int(request.args.get("limit"), 100, maximum=200)
    messages = messages_service.thread(conversation_id, g.user_id, limit=limit)
    # None means "not a participant". 404 rather than 403 so the endpoint does
    # not confirm that a conversation between two other people exists.
    if messages is None:
        return fail("not_found", "השיחה לא נמצאה.")

    messages_service.mark_thread_read(conversation_id, g.user_id)
    return jsonify({"messages": messages}), 200


@bp.get("/conversations/with/<int:user_id>")
@security.require_auth
def conversation_with(user_id: int):
    """Which conversation, if any, this user already has with that person.

    A GET that creates nothing. `conversation_id` is null when they have never
    spoken - the client then composes against `recipient` and the row is
    written by the first message, so opening a profile and changing your mind
    no longer leaves an empty thread in two inboxes.
    """
    if user_id == g.user_id:
        return fail("invalid", "לא ניתן לפתוח שיחה עם עצמך.")

    # Validated here rather than left to a foreign-key violation further down,
    # which surfaced as "you cannot message yourself" - an error about a
    # completely different problem.
    recipient = users_service.get_by_id(user_id)
    if recipient is None or recipient["status"] != "active":
        return fail("not_found", "המשתמש/ת המבוקש לא נמצא.")

    return jsonify(
        {
            "conversation_id": messages_service.find_conversation(g.user_id, user_id),
            "recipient": users_service.public_user(recipient),
        }
    ), 200


@bp.post("/messages")
@security.require_auth
def send_message():
    data = body_of(request)
    body = clean(data.get("body"), messages_service.BODY_MAX_LENGTH)
    try:
        recipient_id = int(data.get("recipient_id"))
    except (TypeError, ValueError):
        return fail("invalid", "הנמען אינו תקין.")

    if not body:
        return fail("invalid", "לא ניתן לשלוח הודעה ריקה.")
    if recipient_id == g.user_id:
        return fail("invalid", "לא ניתן לשלוח הודעה לעצמך.")

    result, message_id = messages_service.send_message(g.user_id, recipient_id, body)
    if result == "not_found":
        return fail("not_found", "הנמען לא נמצא.")
    if result != "ok":
        return fail("invalid", "לא ניתן לשלוח את ההודעה.")

    # The conversation may have been created by this very message, and the
    # client needs its id to open the thread it just started.
    return jsonify(
        {
            "message_id": message_id,
            "conversation_id": messages_service.find_conversation(g.user_id, recipient_id),
        }
    ), 201
