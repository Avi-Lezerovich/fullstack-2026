"""The brain's invariants - the ones that break silently rather than loudly.

`corpus.py` has referenced this file in a comment for a long time without it
existing. The gap mattered: the whole generator is data, and a typo in data
does not raise, it just produces a juror who says "{defendat}" in public.

Nothing here touches the database or the network, and every test forces the
offline path, so this suite runs in a bare checkout with nothing configured.
"""

from __future__ import annotations

import pytest

from app import seed_data
from app.brain import corpus, decide, occasion, offline

ALL_AGENTS = seed_data.all_agents()
TONES_IN_USE = sorted({agent["tone_tag"] for agent in ALL_AGENTS})


# --- the corpus is data, so its integrity has to be asserted ----------------


@pytest.mark.parametrize("task", corpus.TEMPLATES)
def test_every_task_has_templates(task):
    assert corpus.TEMPLATES[task], f"{task} has no templates"


def test_every_template_slot_resolves():
    """A typo in a template surfaces as a literal "{defendat}" in the UI."""
    for task, templates in corpus.TEMPLATES.items():
        for template in templates:
            for slot in offline.slots_in(template):
                assert slot in corpus.BANKS or slot in corpus.CONTEXT_SLOTS, (
                    f"template for {task!r} uses unknown slot {slot!r}"
                )


@pytest.mark.parametrize("tone", TONES_IN_USE)
def test_every_tone_in_use_has_every_bank(tone):
    """A tone missing one bank degrades to silence in that slot, not an error.

    `offline.generate` fills a missing bank with "" and carries on, so a judge
    of an incomplete tone would deliver an empty ruling and nothing would say
    why.
    """
    for slot, banks in corpus.BANKS.items():
        assert banks.get(tone), f"tone {tone!r} has no {slot!r} bank"


def test_no_bank_is_empty():
    for slot, banks in corpus.BANKS.items():
        for tone, phrases in banks.items():
            assert phrases, f"{slot}/{tone} is empty"


# --- the cast ---------------------------------------------------------------


def test_tone_marker_matches_the_declared_tone():
    """`tone_tag` and the [tone:x] inside the prompt must agree.

    They are two copies of one fact - the column drives the UI badge, the
    marker drives the phrase bank - so a mismatch shows one voice and writes
    in another.
    """
    for agent in ALL_AGENTS:
        assert offline.tone_of(agent["personality_prompt"]) == agent["tone_tag"], (
            f"{agent['personality_name']} is tagged {agent['tone_tag']} "
            f"but its prompt resolves to {offline.tone_of(agent['personality_prompt'])}"
        )


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


def test_different_personalities_say_different_things():
    """Two jurors on one case should not produce one sentence twice."""
    context = {"defendant": "יום שני", "charges": ["הפרת שלווה"]}
    said = {
        offline.generate(a["personality_prompt"], "jury_deliberation", context)
        for a in ALL_AGENTS
        if a["role"] == "juror"
    }
    jurors = sum(1 for a in ALL_AGENTS if a["role"] == "juror")
    assert len(said) >= jurors - 1


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
