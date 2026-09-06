# -*- coding: utf-8 -*-
"""Text correction: the assist that must not write anything.

The failure mode this whole file is about is a single one, and it is not an
exception. /assist/draft-lawsuit and /assist/correct-text run through the same
`brain.generate()`, the same prompt builder and the same fallback; the only
things keeping them apart are a character sheet, a task brief, a suppressed
angle and one skipped clean-up. Every one of those is a soft constraint that
still returns a perfectly good-looking 200 when it stops working - the user
simply gets a filing they did not write, handed to them as a correction.

So each of them gets an assertion. Nothing here touches the database or the
network: the endpoint tests use the real Flask app with `_load_user` faked,
which is enough because correction reads no rows at all.
"""

from __future__ import annotations

import pytest

from app import brain, create_app
from app.api import assist
from app.brain import llm, offline

# These live in tests/unit and are hermetic - no database, no network - but
# carried no marker, so `pytest -m unit` silently ran a fraction of the layer.
pytestmark = pytest.mark.unit

FILING = "מוגשת בזאת תביעה נגד השכן מלמעלה.\n\nהוא מזיז רהיטים ב03:00 בלילה.\n\nמתבקש סעד."


@pytest.fixture(autouse=True)
def offline_backend(monkeypatch):
    """Every test here runs with no credentials, like a fresh checkout."""
    monkeypatch.setenv("BRAIN_FORCE_OFFLINE", "1")


@pytest.fixture
def client(monkeypatch):
    """The real app, with authentication faked and no database behind it.

    `require_auth` is the only thing on this endpoint that would touch MySQL,
    and it is a decorator over a single `_load_user` call - so replacing that
    call is the whole of the setup. Nothing in the view reads a row.
    """
    monkeypatch.setattr(
        "app.security._load_user", lambda: {"id": 1, "name": "דנה", "is_admin": False}
    )
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


# --- the offline promise ----------------------------------------------------


def test_offline_correction_returns_the_text_untouched():
    """The honest offline answer, and the reason it is honest.

    There is no model of Hebrew in `offline.py` - it is phrase templates with
    slots - so it cannot correct anything, and the one thing it must never do
    is pretend otherwise by returning something subtly different.
    """
    assert offline.correct_text(FILING) == FILING


def test_offline_correction_keeps_the_paragraphs():
    """The specific way this would have broken.

    `offline.tidy`, which every other task's output goes through, collapses all
    whitespace to single spaces. Run over a correction it silently reflows a
    three-paragraph filing into one - an edit the user never asked for, made by
    the feature whose entire promise is that it changes nothing but spelling.
    """
    assert brain.generate("מגיה", "correct_text", {"user_text": FILING}) == FILING
    assert offline.tidy(FILING) != FILING, "tidy would have flattened this; that is the point"


def test_correction_never_reaches_the_phrase_templates():
    """A filing must not come back as a docket entry.

    Without the branch in `offline.generate` this task falls through to the
    template lookup, finds nothing, and returns the "אין לי מה להוסיף" fallback
    - the user's text replaced by an apology, under a button labelled "fix my
    spelling".
    """
    corrected = offline.generate("מגיה", "correct_text", {"user_text": FILING})
    assert corrected == FILING
    assert "אין לי מה להוסיף" not in corrected


def test_a_registered_task_that_health_and_the_suite_can_see():
    assert "correct_text" in brain.TASKS
    assert "correct_text" in brain.VERBATIM_TASKS


# --- the prompt is a proofreader's, not a drafter's -------------------------


def test_the_correction_brief_countermands_the_house_style():
    """Block 1 of every system prompt tells the model to surprise the reader.

    It is byte-identical across all personalities and tasks - that shared
    prefix is the entire prompt cache - so a proofreading call cannot be given
    a quieter system prompt. It has to be talked out of the house style in its
    own brief, which means the brief has to actually say so.
    """
    brief = llm.TASK_BRIEFS["correct_text"]
    assert "לא כותב" in brief
    assert "לא חלים כאן" in brief, "the brief no longer waives the style rules"


def test_correction_draws_no_angle():
    """MOVES and HOOKS are instructions to be interesting.

    Handed to a proofreader they are an invitation to rewrite, which is the one
    outcome this endpoint exists to avoid. Every other task must still get one,
    or the feed goes back to sounding like one voice.
    """
    assert llm.pick_angle("מגיה", "correct_text", {"user_text": FILING}) == ""
    assert llm.pick_angle("מגיה", "suggest_comment", {"case_body": "x"}) != ""


def test_the_users_text_is_fenced_rather_than_bulleted():
    """A multi-paragraph document cannot be a "- label: value" line.

    Bulleted, the model has no way to see where the user's text stops and the
    instructions resume, and the blank lines inside it read as the end of the
    list.
    """
    prompt = llm.build_prompt("correct_text", {"user_text": FILING})
    assert "<<<\n" + FILING + "\n>>>" in prompt
    assert "- הטקסט" not in prompt


def test_the_proofreader_is_not_the_drafter():
    """The two voices must stay two.

    HOUSE_VOICE is a rewriter by design - "take a small complaint and dress it
    in ceremonial legal Hebrew" - and pointed at text the user already wrote it
    produces a filing they did not write. If correction is ever handed that
    sheet, the two endpoints have quietly become one.
    """
    assert assist.PROOFREADER_VOICE != assist.HOUSE_VOICE
    assert "לא כותב עברית" in assist.PROOFREADER_VOICE
    assert "משפטית" not in assist.PROOFREADER_VOICE.split("מה שלא תעשה")[0]


# --- the endpoint -----------------------------------------------------------


def test_it_corrects_and_says_which_backend_answered(client):
    response = client.post("/api/assist/correct-text", json={"text": FILING})
    assert response.status_code == 200
    assert response.get_json() == {"body": FILING, "backend": "offline"}


def test_empty_text_is_a_hebrew_400(client):
    """Not a 500 and not a silent empty string: `fail("invalid", ...)`."""
    response = client.post("/api/assist/correct-text", json={"text": "   "})
    assert response.status_code == 400
    assert response.get_json()["error"] == "אין טקסט לתיקון."


def test_a_missing_body_is_the_same_400(client):
    """`body_of` turns a malformed request into our own Hebrew error rather
    than Werkzeug's English 415."""
    response = client.post("/api/assist/correct-text")
    assert response.status_code == 400
    assert response.get_json()["code"] == "invalid"


def test_it_is_signed_in_only(monkeypatch):
    """Anonymous callers cannot spend the court's tokens."""
    monkeypatch.setattr("app.security._load_user", lambda: None)
    app = create_app()
    app.config["TESTING"] = True
    response = app.test_client().post("/api/assist/correct-text", json={"text": FILING})
    assert response.status_code == 401


def test_a_filing_at_the_length_limit_survives_the_round_trip(client):
    """The cap is the composer's own, so nothing a user can type is truncated.

    An earlier draft capped the input at the comment limit, which is less than
    half a filing: the correction came back missing its last paragraphs and
    looked like the proofreader had deleted them.
    """
    long_filing = "מילה " * 1500
    response = client.post("/api/assist/correct-text", json={"text": long_filing})
    assert response.status_code == 200
    assert response.get_json()["body"] == long_filing.strip()
