# -*- coding: utf-8 -*-
"""Withdrawing a filing - the one place this application really does DELETE.

This replaces `tests/unit/test_post_deletion.py`, which tested
`app.services.delete_post` against a hand-built SQLite schema. The function
survived the rename as `cases_service.delete_case` and gained a branch the old
one had no concept of: once a jury is seated the record belongs to the court,
so `"closed"` joins ok / forbidden / not_found.

It is an integration test now rather than a unit one, and the reason is the
cascade. The old test asserted that charges disappear with their post - but it
asserted it against SQLite with `PRAGMA foreign_keys = ON`, which proves that
SQLite cascades, not that the production schema does. `ON DELETE CASCADE` on
seven tables pointing at `cases` is an InnoDB property of database/init.sql,
and the only honest way to test it is to run it there.

The contrast with moderation is the point of the file: hiding is a status
transition and reversible, withdrawal is a real DELETE and is not. Everything
below is about keeping those two apart.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


@pytest.fixture
def author(make_user):
    return make_user("התובעת", "author@lolsuit.test")


@pytest.fixture
def stranger(make_user):
    return make_user("עובר אורח", "stranger@lolsuit.test")


# --- the four outcomes ------------------------------------------------------


def test_the_author_can_withdraw_their_own_filing(db, author, make_case):
    from app.services import cases_service

    case_id = make_case(author["id"])

    assert cases_service.delete_case(case_id, author["id"], conn=db) == "ok"
    db.commit()

    assert db.query_one("SELECT id FROM cases WHERE id = %s", (case_id,)) is None


def test_nobody_else_can_withdraw_it_not_even_an_admin(db, author, admin, stranger, make_case):
    """Moderation hides; it never deletes.

    An admin who could delete would be able to destroy the audit trail that
    makes their own decisions reviewable, so `delete_case` deliberately does
    not check `is_admin` at all - it checks authorship and nothing else.
    """
    from app.services import cases_service

    case_id = make_case(author["id"])

    assert cases_service.delete_case(case_id, stranger["id"], conn=db) == "forbidden"
    assert cases_service.delete_case(case_id, admin["id"], conn=db) == "forbidden"

    assert db.query_one("SELECT id FROM cases WHERE id = %s", (case_id,)) is not None


def test_withdrawing_a_case_that_does_not_exist_is_not_found(db, author):
    from app.services import cases_service

    assert cases_service.delete_case(999_999, author["id"], conn=db) == "not_found"


@pytest.mark.parametrize("status", ["jury_deliberation", "verdict_reached", "closed"])
def test_a_filing_cannot_be_withdrawn_once_the_jury_is_seated(db, author, make_case, status):
    """"closed", not "forbidden" - the author had the right, and lost it.

    That distinction reaches the reader: the route maps `closed` to 409 with
    "לא ניתן למשוך תביעה אחרי שהורכב הרכב מושבעים" rather than to a flat 403
    that would read as "this was never yours".
    """
    from app.services import cases_service

    case_id = make_case(author["id"], status=status)

    assert cases_service.delete_case(case_id, author["id"], conn=db) == "closed"
    assert db.query_one("SELECT id FROM cases WHERE id = %s", (case_id,)) is not None


def test_a_case_still_in_the_witness_phase_can_be_withdrawn(db, author, make_case):
    """The boundary from the other side, so "closed" cannot creep backwards.

    `create_case` files straight into `witness_phase`, so this is the state
    every real filing is in for its first trial day - if it were refused here,
    withdrawal would be unreachable in practice.
    """
    from app.services import cases_service

    case_id = make_case(author["id"], status="witness_phase")

    assert cases_service.delete_case(case_id, author["id"], conn=db) == "ok"


# --- the cascade, against the real foreign keys -----------------------------


def test_withdrawing_takes_everything_hanging_off_the_case_with_it(
    db, author, stranger, make_case, make_comment
):
    """Seven tables reference `cases`, and a leftover row in any of them is a
    row nothing can ever reach again.

    This is the assertion that could not be made against the SQLite mirror: the
    cascades are declared in database/init.sql and enforced by InnoDB, and the
    mirror only ever proved that a different database cascades.
    """
    from app.services import cases_service, follows_service, likes_service

    case_id = make_case(author["id"], charges=["גרימת עוגמת נפש", "הפרת אמון"])
    make_comment(case_id, stranger["id"])
    likes_service.toggle_like(case_id, stranger["id"], conn=db)
    follows_service.follow(case_id, stranger["id"], source="manual", conn=db)
    db.commit()

    dependants = {
        "case_charges": "SELECT COUNT(*) FROM case_charges WHERE case_id = %s",
        "comments": "SELECT COUNT(*) FROM comments WHERE case_id = %s",
        "likes": "SELECT COUNT(*) FROM likes WHERE case_id = %s",
        "case_follows": "SELECT COUNT(*) FROM case_follows WHERE case_id = %s",
        "case_activity": "SELECT COUNT(*) FROM case_activity WHERE case_id = %s",
    }
    for table, sql in dependants.items():
        assert db.query_value(sql, (case_id,)) > 0, f"{table} was never populated"

    assert cases_service.delete_case(case_id, author["id"], conn=db) == "ok"
    db.commit()

    for table, sql in dependants.items():
        assert db.query_value(sql, (case_id,)) == 0, f"{table} kept an orphan"


def test_withdrawing_a_filing_does_not_touch_the_people_in_it(
    db, author, stranger, make_case, make_comment
):
    """The cascade runs one way only.

    `comments.author_id` also carries ON DELETE CASCADE, which is what makes
    deleting a *user* remove their comments - the direction that must not also
    mean "deleting a case removes its commenters".
    """
    from app.services import cases_service

    case_id = make_case(author["id"])
    make_comment(case_id, stranger["id"])
    db.commit()

    cases_service.delete_case(case_id, author["id"], conn=db)
    db.commit()

    assert db.query_value("SELECT COUNT(*) FROM users WHERE id = %s", (stranger["id"],)) == 1
    assert db.query_value("SELECT COUNT(*) FROM users WHERE id = %s", (author["id"],)) == 1


@pytest.mark.xfail(
    reason=(
        "database/init.sql documents a `fk_cases_defendant ... ON DELETE SET NULL` "
        "at length but never declares it - `cases` has exactly one foreign key, "
        "fk_cases_author. Reported rather than fixed."
    ),
    strict=True,
)
def test_a_lawsuit_naming_someone_survives_that_person_being_deleted(db, author, make_case):
    """`defendant_user_id` should be SET NULL where everything else cascades.

    Deleting an account must not erase the lawsuits filed *against* it - that
    would make deleting yourself a way to destroy the record of what you were
    accused of - but it must not leave the case pointing at an id that is gone
    either, because MySQL reuses ids and the filing would silently re-aim
    itself at whoever gets that number next.

    init.sql spends six lines explaining that this column carries SET NULL and
    why that ruled out a CHECK constraint. The constraint itself is missing;
    only `KEY idx_cases_defendant` survives, so the comment sits above an
    index that enforces nothing. Nothing in the application deletes a user
    today, which is why it has gone unnoticed - the day account deletion ships,
    it is live.

    Marked strict, so this starts failing the moment the constraint is added
    and the marker can come off with it.
    """
    from app.services import cases_service

    db.execute(
        "INSERT INTO users (name, email, password_hash, is_admin, is_bot, status, created_at) "
        "VALUES ('הנתבע', 'defendant@lolsuit.test', 'x', 0, 0, 'active', UTC_TIMESTAMP())"
    )
    defendant = db.query_value("SELECT id FROM users WHERE email = 'defendant@lolsuit.test'")
    db.commit()

    result, case_id = cases_service.create_case(
        author["id"],
        "תביעה נגד מישהו שקיים",
        "הוא לקח את הכיסא.",
        "הנתבע",
        defendant_user_id=defendant,
        screen=False,
        conn=db,
    )
    assert result == "ok"
    db.commit()

    db.execute("DELETE FROM users WHERE id = %s", (defendant,))
    db.commit()

    row = db.query_one(
        "SELECT id, defendant_user_id, defendant_text FROM cases WHERE id = %s", (case_id,)
    )
    assert row is not None
    assert row["defendant_user_id"] is None
    assert row["defendant_text"] == "הנתבע"
