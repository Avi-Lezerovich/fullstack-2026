# -*- coding: utf-8 -*-
"""The writing-help endpoints, and the liveness probe.

Two blueprints in one file because they share the property that makes them
worth testing at all: neither writes anything, and both are the places where a
mistake is silent rather than loud.

**Assist.** Three endpoints that generate text and one that borrows a
personality. Nothing here reaches the database, and nothing here publishes - a
suggestion goes back into the composer the user was already filling in and
reaches the database through the ordinary publish path, moderation scan
included. The endpoints run offline throughout (conftest sets
`BRAIN_FORCE_OFFLINE=1`), which is not a limitation of the test: the offline
generator is the default rather than a fallback, precisely so the feature works
in a fresh checkout with nothing configured.

The one worth care is `/assist/correct-text`. It is the endpoint that is *not*
writing, and the source spends a paragraph on why it has its own voice: pointed
at text the user has already written, the house drafter would hand back prose
they did not write in a register they did not choose. Its budget is derived
from the input for the same reason - a fixed one would cap the model mid-filing
and the truncation would look like the proofreader deleting two paragraphs.

**Health.** The one blueprint allowed to run its own SQL, because its whole job
is reporting whether *this* process can reach the database. It also reports the
worker's tick counter, which is the only way "is the trial engine actually
advancing" is visible from outside a container that shares nothing but MySQL.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


@pytest.fixture
def author(make_user):
    return make_user("התובעת", "author@lolsuit.test")


@pytest.fixture
def as_author(client, author, signed_in):
    signed_in(author)
    return client


@pytest.fixture
def a_bot(db):
    return db.query_one(
        "SELECT user_id, personality_name FROM agents WHERE role = 'judge' LIMIT 1"
    )


# --- drafting ---------------------------------------------------------------


def test_a_filing_can_be_drafted_from_a_defendant_alone(as_author):
    """The minimum a user has to have typed for the button to do anything."""
    response = as_author.post(
        "/api/assist/draft-lawsuit", json={"defendant_text": "השכן מלמעלה"}
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["body"].strip()
    # Offline throughout, and the endpoint says so rather than implying a model
    # answered. The two disagreed silently in production for weeks.
    assert payload["backend"] == "offline"


def test_the_draft_reads_whatever_the_composer_already_holds(as_author):
    """Title, charges and the free-text hint all reach the generator.

    A drafter given only the defendant's name has to invent the story, which is
    the bug the richer context exists to avoid.
    """
    response = as_author.post(
        "/api/assist/draft-lawsuit",
        json={
            "defendant_text": "השכן מלמעלה",
            "title": "התביעה נגד רעש הרהיטים",
            "hint": "הוא מזיז רהיטים בשלוש לפנות בוקר.",
            "charges": ["הפרעה למנוחת הציבור"],
        },
    )

    assert response.status_code == 200
    assert response.get_json()["body"].strip()


def test_drafting_with_an_empty_composer_is_refused(as_author):
    """Nothing to work from, so there is nothing to invent from either.

    Refused rather than answered with a generic filing, which would be the
    same filing for every user who pressed the button first.
    """
    assert as_author.post("/api/assist/draft-lawsuit", json={}).status_code == 400
    assert as_author.post(
        "/api/assist/draft-lawsuit", json={"defendant_text": "  ", "title": ""}
    ).status_code == 400


def test_nothing_a_draft_touches_is_written_to_the_database(as_author, db):
    """A suggestion is a suggestion: the user still has to submit it."""
    before = db.query_value("SELECT COUNT(*) FROM cases")

    as_author.post("/api/assist/draft-lawsuit", json={"defendant_text": "השכן"})

    assert db.query_value("SELECT COUNT(*) FROM cases") == before


# --- suggesting a comment ---------------------------------------------------


def test_a_comment_can_be_suggested_for_a_case_the_user_is_reading(
    as_author, author, make_case
):
    case_id = make_case(author["id"], title="התביעה נגד יום שני")

    response = as_author.post("/api/assist/suggest-comment", json={"case_id": case_id})

    assert response.status_code == 200
    assert response.get_json()["body"].strip()


def test_suggesting_a_comment_on_a_case_that_is_not_there_is_a_404(as_author):
    assert as_author.post(
        "/api/assist/suggest-comment", json={"case_id": 999_999}
    ).status_code == 404


def test_a_malformed_case_id_is_a_400(as_author):
    for payload in ({}, {"case_id": "abc"}, {"case_id": None}):
        assert as_author.post("/api/assist/suggest-comment", json=payload).status_code == 400


def test_no_comment_is_suggested_for_a_case_the_user_may_not_see(
    as_author, db, admin, author, make_user, make_case, app
):
    """It goes through `get_case` with the viewer's own id, so the visibility
    rule is the same one the case page applies.

    Otherwise the endpoint would read a hidden filing aloud to anybody who
    guessed its id.
    """
    from app.services import moderation_service

    stranger = make_user("זר", "stranger@lolsuit.test")
    hidden = make_case(stranger["id"], title="תיק מוסתר")
    moderation_service.set_content_status(
        "case", hidden, "hidden", actor_id=admin["id"], conn=db
    )
    db.commit()

    assert as_author.post(
        "/api/assist/suggest-comment", json={"case_id": hidden}
    ).status_code == 404


# --- correcting what the user wrote -----------------------------------------


def test_correction_hands_back_text_rather_than_inventing_any(as_author):
    """The endpoint that is not writing.

    Offline, the proofreader is a no-op - which is the correct offline
    behaviour: with no model available, the honest correction of a user's text
    is their text.
    """
    original = "מוגשת בזאת תביעה נגד השכן מלמעלה שמזיז רהיטים בלילה."

    response = as_author.post("/api/assist/correct-text", json={"text": original})

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["body"] == original
    assert payload["backend"] == "offline"


def test_correction_keeps_the_shape_of_what_it_was_given(as_author):
    """Paragraphs survive. A correction that reflowed the text would be a
    rewrite wearing a correction's name."""
    original = "פסקה ראשונה.\n\nפסקה שנייה.\n\nפסקה שלישית."

    body = as_author.post("/api/assist/correct-text", json={"text": original}).get_json()["body"]

    assert body.count("\n\n") == original.count("\n\n")


def test_correcting_nothing_is_refused(as_author):
    for payload in ({}, {"text": ""}, {"text": "   \n  "}):
        assert as_author.post("/api/assist/correct-text", json=payload).status_code == 400


def test_a_long_filing_is_not_truncated_on_the_way_in_or_out(as_author):
    """The input cap is the longest thing any composer on the site can hold.

    Capping at less would silently drop the end of a long filing and return the
    truncation as a correction - the user's own last paragraph, deleted and
    presented as an improvement.
    """
    from app.api.cases import BODY_MAX_LENGTH

    original = "א" * (BODY_MAX_LENGTH - 100)

    body = as_author.post("/api/assist/correct-text", json={"text": original}).get_json()["body"]

    assert len(body) == len(original)


def test_anything_past_the_ceiling_is_held_to_it_at_both_ends(as_author):
    """A model that loops must not hand the composer more text than the
    composer can submit."""
    from app.api.cases import BODY_MAX_LENGTH

    body = as_author.post(
        "/api/assist/correct-text", json={"text": "א" * (BODY_MAX_LENGTH + 500)}
    ).get_json()["body"]

    assert len(body) <= BODY_MAX_LENGTH


# --- borrowing a personality ------------------------------------------------


def test_text_can_be_rewritten_in_a_named_personality(as_author, a_bot):
    """The same seam the bots use, exposed for fun - and it names who spoke."""
    response = as_author.post(
        "/api/assist/in-character",
        json={"agent_user_id": a_bot["user_id"], "hint": "השכן מזיז רהיטים בלילה"},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["body"].strip()
    assert payload["personality_name"] == a_bot["personality_name"]


def test_asking_for_a_character_that_is_not_in_the_cast_is_a_404(as_author, author):
    """An ordinary user is not a personality: `get_agent` joins `agents`, so a
    human id finds nothing."""
    assert as_author.post(
        "/api/assist/in-character", json={"agent_user_id": 999_999}
    ).status_code == 404
    assert as_author.post(
        "/api/assist/in-character", json={"agent_user_id": author["id"]}
    ).status_code == 404


def test_asking_without_naming_a_character_is_a_400(as_author):
    for payload in ({}, {"agent_user_id": "abc"}, {"hint": "משהו"}):
        assert as_author.post("/api/assist/in-character", json=payload).status_code == 400


def test_every_assist_endpoint_needs_a_session(client):
    """Generation costs money once a model is configured, so it is not open."""
    for path in (
        "/api/assist/draft-lawsuit",
        "/api/assist/suggest-comment",
        "/api/assist/correct-text",
        "/api/assist/in-character",
    ):
        assert client.post(path, json={}).status_code == 401, path


# --- health -----------------------------------------------------------------


def test_health_reports_the_database_as_up_and_answers_200(client):
    response = client.get("/api/health")

    assert response.status_code == 200
    body = response.get_json()
    assert body["status"] == "ok"
    assert body["database"] == "up"
    assert body["server_time"]


def test_health_reports_the_brains_intent_and_its_outcome_separately(client):
    """"configured" is what the settings say we will try; "last_backend" is
    what actually answered last.

    They disagreed silently in production for weeks: credentials were set, the
    endpoint said the model backend was live, and every single call was raising
    ModuleNotFoundError and falling back to the offline generator.
    """
    brain = client.get("/api/health").get_json()["brain"]

    assert "configured" in brain
    assert "last_backend" in brain


def test_health_is_the_only_window_onto_a_worker_in_another_container(client, db):
    """The worker shares nothing with the web process but MySQL.

    It records every tick in `worker_state`, so this endpoint can answer "is
    the trial engine advancing" with no cross-process channel at all.
    """
    from worker import loop

    assert client.get("/api/health").get_json()["worker"]["tick_count"] == 0

    loop.tick()
    loop.tick()

    worker = client.get("/api/health").get_json()["worker"]
    assert worker["tick_count"] == 2
    assert worker["last_tick_at"] is not None
    assert worker["seconds_since_tick"] is not None
    assert worker["last_error"] is None


def test_health_reports_a_worker_that_has_never_ticked_without_pretending(client, db):
    """A fresh deployment, where `last_tick_at` is NULL.

    "seconds since the last tick" of a tick that never happened is not zero,
    and reporting zero would make a dead worker look busy.
    """
    worker = client.get("/api/health").get_json()["worker"]

    assert worker["tick_count"] == 0
    assert worker["last_tick_at"] is None
    assert worker["seconds_since_tick"] is None


def test_health_surfaces_the_workers_last_failure(client, db):
    """`stamp_tick` records the error, and this is where anybody sees it.

    Without it a worker failing every tick is indistinguishable from one with
    nothing to do.
    """
    from app.db import connect
    from worker import loop

    connection = connect()
    try:
        loop.stamp_tick(connection, error="the court is on fire")
    finally:
        connection.close()

    assert client.get("/api/health").get_json()["worker"]["last_error"] == "the court is on fire"


def test_health_needs_no_session(client):
    """A probe that needed one could not report that the database is down,
    because resolving the session is the thing that would fail."""
    assert client.get("/api/health").status_code == 200
