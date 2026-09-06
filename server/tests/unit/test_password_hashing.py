# -*- coding: utf-8 -*-
"""Password hashing, and the validation that has to happen before it.

This file used to import `app.utils`, which has not existed since the MySQL
migration. The functions themselves survived the move to `app/security.py`
unchanged, so the behaviour is worth keeping - but the module also gained
something the old tests could not have covered: `password_problem`.

That function exists because **bcrypt 5 raises rather than truncating**. Older
bcrypt silently threw away everything past 72 bytes, which meant a 200-character
password quietly became its first 72 and still worked. Version 5 refuses, so an
over-long password that reaches `hash_password` is a 500 rather than a 400 -
and in Hebrew, where every letter is two bytes, 72 bytes is only 36 characters.
The length has to be judged *before* hashing, and that is what this pins down.

Pure functions: no database, no Flask, no network.
"""

from __future__ import annotations

import pytest

from app import security

pytestmark = pytest.mark.unit

PASSWORD = "correct-horse-battery"

# A bcrypt hash of PASSWORD, precomputed so the verify-only tests below do not
# pay for hashing twice.
KNOWN_HASH = "$2b$04$DnT2Plr51j/5V8YsvfHuYOWeWEOi5zlbFOrks8zL6J8jjuvlY.5U6"


@pytest.fixture(autouse=True)
def cheap_rounds(monkeypatch):
    """Four rounds, not twelve.

    `get_settings()` re-reads the environment every call, so this takes effect
    without patching a single application object.
    """
    monkeypatch.setenv("BCRYPT_ROUNDS", "4")


# --- hashing ----------------------------------------------------------------


def test_a_stored_password_is_never_the_password():
    hashed = security.hash_password(PASSWORD)

    assert isinstance(hashed, str)
    assert hashed != PASSWORD
    assert PASSWORD not in hashed


def test_the_hash_is_bcrypt_and_carries_its_own_cost():
    """The format matters: it is what lets the cost be raised later.

    bcrypt stores the round count inside the digest, so an old hash keeps
    verifying at its original cost after BCRYPT_ROUNDS is raised for new ones.
    A digest that did not say `$2b$` would have lost that.
    """
    hashed = security.hash_password(PASSWORD)

    assert hashed.startswith("$2b$")
    assert len(hashed) == 60


def test_the_configured_cost_is_the_cost_that_is_used():
    """BCRYPT_ROUNDS is honoured, and honoured per call rather than at import.

    Without this, lowering the cost for the test suite would look like it
    worked while every hash still cost twelve rounds.
    """
    import os

    os.environ["BCRYPT_ROUNDS"] = "5"
    assert security.hash_password(PASSWORD).startswith("$2b$05$")

    os.environ["BCRYPT_ROUNDS"] = "4"
    assert security.hash_password(PASSWORD).startswith("$2b$04$")


def test_the_same_password_twice_gives_two_different_hashes():
    """A per-hash salt is what makes two identical passwords indistinguishable
    in a stolen database dump."""
    first = security.hash_password(PASSWORD)
    second = security.hash_password(PASSWORD)

    assert first != second
    assert security.verify_password(PASSWORD, first)
    assert security.verify_password(PASSWORD, second)


def test_a_hebrew_password_survives_the_round_trip():
    """The UI is Hebrew, so the encode/decode pair is on the common path, not
    an edge case."""
    hebrew = "סיסמה־עברית־ארוכה"

    assert security.verify_password(hebrew, security.hash_password(hebrew))


# --- verifying --------------------------------------------------------------


def test_the_right_password_verifies_and_the_wrong_one_does_not():
    assert security.verify_password(PASSWORD, KNOWN_HASH)
    assert not security.verify_password("something-else", KNOWN_HASH)


def test_verification_is_case_sensitive():
    assert not security.verify_password(PASSWORD.upper(), KNOWN_HASH)


@pytest.mark.parametrize(
    "stored",
    ["", "not-a-hash", "$2b$12$too-short", "$2b$04$" + "!" * 53],
    ids=["empty", "garbage", "truncated", "wrong-alphabet"],
)
def test_a_malformed_stored_hash_is_a_failed_login_not_a_crash(stored):
    """A corrupt row must read as "wrong password", not as a 500.

    A user whose row was damaged by a bad migration should see the login form
    again, and an attacker should not be able to tell the difference between a
    damaged account and a wrong guess.

    Only strings are tried, because only strings can arrive: `password_hash` is
    `VARCHAR(255) NOT NULL`, so neither NULL nor a number can come back from
    the column. `verify_password` catches ValueError and TypeError, which is
    exactly the set bcrypt raises for a badly shaped string - widening it to
    guard against a value the schema forbids would be guarding against nothing.
    """
    assert security.verify_password(PASSWORD, stored) is False


def test_an_overlong_password_fails_verification_rather_than_raising():
    """bcrypt 5 raises past 72 bytes even when only checking.

    So the guard is needed on the login path too, not only on signup - and
    `verify_password` swallowing it is what stops a deliberately huge password
    field from being a one-request denial of service.
    """
    assert security.verify_password("a" * 200, KNOWN_HASH) is False


# --- the check that has to come first ---------------------------------------


def test_a_password_shorter_than_the_minimum_is_refused_with_a_reason():
    problem = security.password_problem("a" * (security.MIN_PASSWORD_LENGTH - 1))

    assert problem is not None
    assert str(security.MIN_PASSWORD_LENGTH) in problem


def test_a_password_at_the_minimum_is_accepted():
    """The boundary is inclusive, so the message and the rule agree."""
    assert security.password_problem("a" * security.MIN_PASSWORD_LENGTH) is None


def test_the_length_limit_is_counted_in_bytes_not_characters():
    """36 Hebrew characters are 72 bytes, and 37 are 74.

    This is the whole reason the limit is expressed in bytes: a character count
    would accept a Hebrew password that bcrypt then refuses to hash.
    """
    at_the_limit = "א" * 36
    over_the_limit = "א" * 37

    assert len(at_the_limit.encode("utf-8")) == security.MAX_PASSWORD_BYTES
    assert security.password_problem(at_the_limit) is None
    assert security.password_problem(over_the_limit) is not None


def test_everything_password_problem_accepts_can_actually_be_hashed():
    """The contract between the two functions, stated as a test.

    `password_problem` is only worth having if it is exactly the set of inputs
    `hash_password` survives. Anything it waves through that bcrypt then
    rejects is a 500 on the signup endpoint.
    """
    for candidate in ["12345678", "א" * 36, "x" * 72, "סיסמה ארוכה מספיק"]:
        assert security.password_problem(candidate) is None
        assert security.verify_password(candidate, security.hash_password(candidate))
