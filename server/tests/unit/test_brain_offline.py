"""The brain's invariants - the ones that break silently rather than loudly.

`corpus.py` has referenced this file in a comment for a long time without it
existing. The gap mattered: the whole generator is data, and a typo in data
does not raise, it just produces a juror who says "{defendat}" in public.

Nothing here touches the database or the network, and every test forces the
offline path, so this suite runs in a bare checkout with nothing configured.
"""

from __future__ import annotations

import pytest

from app import brain, seed_data
from app.brain import corpus, decide, occasion, offline

ALL_AGENTS = seed_data.all_agents()


# --- the corpus is data, so its integrity has to be asserted ----------------


@pytest.mark.parametrize("task", corpus.TEMPLATES)
def test_every_task_has_templates(task):
    assert corpus.TEMPLATES[task], f"{task} has no templates"


def test_every_template_slot_resolves():
    """A typo in a template surfaces as a literal "{defendat}" in the UI.

    Sharper than it used to be: with the tone banks gone, every slot has to be
    a CONTEXT slot, so this now says "the only variable parts of a minute come
    from the case" rather than merely "this name is known somewhere".
    """
    for task, templates in corpus.TEMPLATES.items():
        for template in templates:
            for slot in offline.slots_in(template):
                assert slot in corpus.CONTEXT_SLOTS, (
                    f"template for {task!r} uses unknown slot {slot!r}"
                )


def test_every_brain_task_can_be_written_offline():
    """The zero-credential path must cover every task, not most of them.

    A task with no template falls through to "אין לי מה להוסיף", which is a
    juror going silent in a trial that has to reach a verdict. `bot_comment_reply`
    was added long after this file and would have been missed.
    """
    for task in brain.TASKS:
        assert task in corpus.TEMPLATES, f"{task} has no offline minute"


def test_the_stenographer_does_not_impersonate_anyone():
    """The point of the rewrite, pinned.

    Two personalities as unlike each other as this file contains, on one case,
    must produce lines that read as the same clerk writing - not as two
    characters. First person singular is the tell: a minute has no "I" in it,
    and the moment one appears the fallback is auditioning again.
    """
    context = {"defendant": "המדפסת", "charges": ["גרימת עייפות"]}
    for agent in ALL_AGENTS:
        text = offline.generate(agent["personality_prompt"], "jury_deliberation", context)
        for tell in ("אני ", "אני,", "שלי ", "תראו", "בימיי"):
            assert tell not in text, (
                f"the offline minute for {agent['personality_name']} reads as a "
                f"person speaking, not as a record: {text!r}"
            )


# --- the cast ---------------------------------------------------------------


def test_every_personality_has_exemplars():
    """Three lines the character actually said.

    A described voice converges with every other voice fitting the description;
    an exemplar does not. These are the whole of what makes two `pedantic`
    jurors distinguishable at output number one hundred, and a personality
    added without them regresses silently - it still works, it just sounds like
    the others.
    """
    for agent in ALL_AGENTS:
        prompt = agent["personality_prompt"]
        assert "דברים שאמרת כאן בעבר" in prompt, (
            f"{agent['personality_name']} has no exemplar lines"
        )
        assert prompt.count('\n- "') >= 2, (
            f"{agent['personality_name']} has fewer than two exemplars"
        )


def test_no_personality_still_carries_the_dead_tone_marker():
    """`[tone:x]` selected a phrase bank that no longer exists.

    Left in, it would ride along inside the cached character block on every
    single call, meaning nothing and costing tokens - and the next reader would
    spend an afternoon looking for what consumes it.
    """
    for agent in ALL_AGENTS:
        assert "[tone:" not in agent["personality_prompt"], agent["personality_name"]


def test_slugs_and_emails_are_unique():
    """The email is the seeding upsert's natural key; a collision merges bots."""
    emails = [agent["email"] for agent in ALL_AGENTS]
    assert len(set(emails)) == len(emails)


def test_judges_have_a_tiebreak_and_jurors_have_a_bias():
    for agent in ALL_AGENTS:
        if agent["role"] == "judge":
            assert agent.get("tiebreak_lean") in ("guilty", "not_guilty")
        if agent["role"] == "juror":
            assert 0.0 <= float(agent["guilt_bias"]) <= 1.0


def test_enough_jurors_to_seat_a_panel():
    jurors = [a for a in ALL_AGENTS if a["role"] == "juror"]
    # jury_service.PANEL_SIZE is 7; below that seat_panel returns None and
    # cases silently stall in the witness phase.
    assert len(jurors) >= 7


# --- generation -------------------------------------------------------------


@pytest.mark.parametrize("agent", ALL_AGENTS, ids=lambda a: a["slug"])
def test_every_personality_generates_for_every_task(agent):
    context = {
        "case_title": "התביעה נגד הקפה שהתקרר",
        "defendant": "הקפה שהתקרר",
        "charges": ["גניבת דעת", "עוגמת נפש"],
        "verdict": "guilty",
        "tally_guilty": 5,
        "tally_not_guilty": 2,
    }
    for task in corpus.TEMPLATES:
        text = offline.generate(agent["personality_prompt"], task, context)
        assert text and text.strip()
        # An unfilled placeholder is the failure this whole module exists for.
        assert "{" not in text and "}" not in text, f"{agent['slug']}/{task}: {text}"


def test_generation_is_deterministic():
    """Retrying a crashed worker tick must reproduce the identical comment.

    The dedupe key and the text are written separately, so a generator that
    drifted between attempts would leave the two disagreeing.
    """
    prompt = ALL_AGENTS[0]["personality_prompt"]
    context = {"defendant": "יום שני", "charges": ["הפרת שלווה"]}
    first = offline.generate(prompt, "jury_deliberation", context)
    assert first == offline.generate(prompt, "jury_deliberation", context)


def test_a_seated_panel_does_not_read_as_a_stuck_printer():
    """Seven jurors on one case must not file one line seven times.

    The bar here is deliberately much lower than it used to be, and the change
    is the point rather than a regression. The old assertion was "twenty jurors
    produce twenty distinct sentences", which the phrase bank could meet
    because it was pretending to be twenty people. A minute is not pretending:
    the same clerical sentence recurring across cases is what a docket looks
    like, and demanding otherwise is what pushed this file toward impersonation
    in the first place.

    What still has to hold is legibility. Seven identical consecutive lines
    read as a bug in the site, not as a record - so a full panel gets checked,
    at panel size, and nothing larger is claimed.
    """
    context = {"defendant": "יום שני", "charges": ["הפרת שלווה"]}
    jurors = [a for a in ALL_AGENTS if a["role"] == "juror"][:7]
    said = {
        offline.generate(a["personality_prompt"], "jury_deliberation", context)
        for a in jurors
    }
    assert len(said) >= 4, said


def test_trim_never_returns_empty():
    assert offline.trim("", 100)
    assert offline.trim("   ", 100)


def test_trim_cuts_on_a_word_boundary():
    trimmed = offline.trim("א" * 10 + " " + "ב" * 50, 20)
    assert len(trimmed) <= 21  # the ellipsis is one char past the limit
    assert trimmed.endswith("…")


# --- filings ----------------------------------------------------------------


def test_offline_filings_never_name_a_person():
    """A bot may sue a thing. It may never sue a human.

    The offline path guarantees this by construction - it draws only from
    LAWSUIT_DEFENDANTS - and this test is what keeps a person's name from being
    added to that list by accident.
    """
    for agent in ALL_AGENTS:
        filing = offline.invent_lawsuit(agent["personality_prompt"], agent["slug"])
        assert filing["defendant_text"] in corpus.LAWSUIT_DEFENDANTS


@pytest.mark.parametrize(
    "target,expected",
    [
        ({"kind": "bot", "name": "מלכת הדרמה"}, "מלכת הדרמה"),
        ({"kind": "topical", "subjects": ["גל החום של אוגוסט"]}, "גל החום של אוגוסט"),
    ],
)
def test_filings_honour_the_target(target, expected):
    filing = offline.invent_lawsuit(ALL_AGENTS[0]["personality_prompt"], "1:2", target)
    assert filing["defendant_text"] == expected
    assert expected in filing["title"]


def test_a_filing_does_not_quote_its_own_title_back():
    """The body used to echo the headline it was generated from."""
    for agent in ALL_AGENTS[:8]:
        filing = offline.invent_lawsuit(agent["personality_prompt"], agent["slug"])
        assert filing["title"] not in filing["body"]


def test_filings_are_complete_enough_to_insert():
    filing = offline.invent_lawsuit(ALL_AGENTS[0]["personality_prompt"], "x")
    assert filing["title"] and filing["body"] and filing["defendant_text"]
    assert 1 <= len(filing["charges"]) <= 3


# --- decisions --------------------------------------------------------------


def test_votes_are_reproducible():
    kwargs = dict(guilt_bias=0.5, case_id=1, juror_user_id=2, salt="s")
    assert decide.decide_vote(**kwargs) == decide.decide_vote(**kwargs)


def test_guilt_bias_extremes_are_respected():
    always = [
        decide.decide_vote(guilt_bias=1.0, case_id=c, juror_user_id=1, salt="s")
        for c in range(30)
    ]
    never = [
        decide.decide_vote(guilt_bias=0.0, case_id=c, juror_user_id=1, salt="s")
        for c in range(30)
    ]
    assert set(always) == {decide.GUILTY}
    assert set(never) == {decide.NOT_GUILTY}


def test_action_and_target_weights_sum_to_one():
    for options in (decide.SOCIAL_ACTIONS, decide.LAWSUIT_TARGETS):
        assert sum(weight for _, weight in options) == pytest.approx(1.0)


def test_lawsuit_target_is_reproducible_and_covers_every_kind():
    kwargs = dict(agent_user_id=3, tick=9, salt="s")
    assert decide.decide_lawsuit_target(**kwargs) == decide.decide_lawsuit_target(**kwargs)
    seen = {
        decide.decide_lawsuit_target(agent_user_id=u, tick=t, salt="s")
        for u in range(12)
        for t in range(12)
    }
    assert seen == {"thing", "topical", "bot"}


# --- topical subjects -------------------------------------------------------


@pytest.mark.parametrize("month", range(1, 13))
def test_every_month_has_topical_subjects(month):
    from datetime import datetime

    now = datetime(2026, month, 15, 12, 0)
    assert occasion.current_subjects(now)
    assert occasion.describe(now)


def test_operator_subjects_lead():
    from datetime import datetime

    subjects = occasion.current_subjects(datetime(2026, 8, 29, 12, 0), ("שביתת הרכבת",))
    assert subjects[0] == "שביתת הרכבת"


def test_local_now_shifts_off_utc():
    """Israel is never on UTC, so the hour buckets must not run on it."""
    from datetime import datetime

    utc = datetime(2026, 8, 29, 9, 21)
    assert occasion.local_now(utc).hour != utc.hour


# --- who may sit on a case --------------------------------------------------
#
# `pool_ids` takes an optional connection, and the wrapper around it only ever
# calls `query_all` - so a stub is enough to test the disqualification rule
# without a database.


class _StubDb:
    def __init__(self, user_ids):
        self._rows = [{"user_id": uid} for uid in user_ids]

    def query_all(self, sql, params=()):
        return self._rows


def test_pool_ids_disqualifies_the_parties_to_a_case():
    """A bot must never be seated on a case it is a party to.

    Bots sue each other now, so the defendant of a case can be an agent. Until
    this exclusion existed the draw could seat that defendant on their own
    jury - or let them preside over their own trial.
    """
    from app.services import agents_service

    db = _StubDb([1, 2, 3, 4, 5])
    assert agents_service.pool_ids("juror", conn=db) == [1, 2, 3, 4, 5]
    assert agents_service.pool_ids("juror", conn=db, exclude=(2, 4)) == [1, 3, 5]
    # A human plaintiff has no agent row, and defendant_user_id is often NULL.
    assert agents_service.pool_ids("juror", conn=db, exclude=(None, 99)) == [1, 2, 3, 4, 5]


def test_the_pools_stay_large_enough_after_disqualification():
    """Excluding both parties must not starve the draw.

    `select_panel` needs PANEL_SIZE jurors and at least one judge; if either
    pool falls short it returns None and the case stalls in the witness phase.
    """
    jurors = sum(1 for a in ALL_AGENTS if a["role"] == "juror")
    judges = sum(1 for a in ALL_AGENTS if a["role"] == "judge")
    assert jurors - 2 >= 7
    assert judges - 2 >= 1
