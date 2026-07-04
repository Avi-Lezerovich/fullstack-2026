"""Unit tests — password hashing (the pyramid base).

Target under test: server/app/utils.py -> hash_password() / verify_password().
These are pure functions: no database, no network, no Flask. Just bcrypt. That
makes them Fast, Independent, Repeatable, Self-validating (F.I.R.S.T.), and every
test follows Arrange -> Act -> Assert.
"""
import pytest

from app.utils import hash_password, verify_password

# Shared, immutable test inputs. `hashed_password` is a precomputed bcrypt hash of
# `password`, so the verify-only tests skip the (slow) hashing step in Arrange.
password = "password123"
hashed_password = "$2b$12$ZYM3GDU8SFRJ2T2JTXuJQ.7bwXVo23OBz76b5LhSQWQ.TH/LDceee"


@pytest.mark.unit
def test_hash_password_does_not_return_plaintext():
    # Act — hash it.
    hashed = hash_password(password)

    # Assert — we stored something, and it is NOT the raw password.
    assert isinstance(hashed, str)
    assert hashed != password


@pytest.mark.unit
def test_hash_is_bcrypt_format():
    # Act
    hashed = hash_password(password)

    # Assert — bcrypt hashes start with the "$2b$" identifier and are 60 chars long.
    # This documents *which* algorithm we rely on (a security-relevant fact).
    assert hashed.startswith("$2b$")
    assert len(hashed) == 60


@pytest.mark.unit
def test_verify_password_accepts_correct_password():
    # Act — verify the SAME password against its precomputed hash.
    result = verify_password(password, hashed_password)

    # Assert — the correct password is accepted (the positive half of login).
    assert result is True


@pytest.mark.unit
def test_verify_password_rejects_wrong_password():
    # Act — verify a DIFFERENT password against it.
    result = verify_password("wrong-password", hashed_password)

    # Assert — the wrong password is rejected (the negative half of login).
    assert result is False


@pytest.mark.unit
def test_verify_password_is_case_sensitive():
    # Act — the same characters as the real password, different case.
    result = verify_password("PASSWORD123", hashed_password)

    # Assert — passwords are case-sensitive: "PASSWORD123" must not unlock
    # an account whose password is "password123".
    assert result is False


@pytest.mark.unit
def test_same_password_produces_different_hashes_but_both_verify():
    # Arrange / Act — hash the SAME password twice.
    first = hash_password(password)
    second = hash_password(password)

    # Assert — bcrypt generates a fresh salt for every hash, so the two strings
    # differ (defeats rainbow tables and hides that two users share a password)...
    assert first != second
    # ...yet BOTH still verify against the original password.
    assert verify_password(password, first) is True
    assert verify_password(password, second) is True


@pytest.mark.unit
def test_unicode_password_round_trips():
    # Arrange — a Hebrew password with spaces and punctuation. The app's UI is
    # Hebrew, so non-ASCII passwords are the norm here, not an edge case; hashing
    # utf-8-encodes the string before bcrypt sees it.
    hebrew_password = "סיסמה חזקה 123!"

    # Act
    hashed = hash_password(hebrew_password)

    # Assert — the exact same unicode string verifies against its own hash.
    assert verify_password(hebrew_password, hashed) is True


@pytest.mark.unit
def test_hash_password_rejects_passwords_longer_than_72_bytes():
    # Arrange — one byte past bcrypt's 72-byte input limit.
    too_long = "x" * 73

    # Act + Assert — bcrypt >= 5 refuses (older versions silently truncated!), so
    # hash_password propagates ValueError. This pins the contract: callers must
    # validate length BEFORE hashing — the signup route returns 400 for this.
    with pytest.raises(ValueError):
        hash_password(too_long)


@pytest.mark.unit
def test_verify_password_returns_false_for_overlong_password():
    # Act — a >72-byte password attempted against a valid stored hash (login path).
    result = verify_password("x" * 100, hashed_password)

    # Assert — bcrypt raises internally, but login must see a clean False, not a crash.
    assert result is False


@pytest.mark.unit
def test_verify_password_returns_false_for_malformed_hash():
    # Arrange — a stored value that is NOT a valid bcrypt hash (e.g. legacy/corrupt row).
    garbage = "not--bcrypt-hash"

    # Act — verify against the garbage; bcrypt raises internally.
    result = verify_password(password, garbage)

    # Assert — the function swallows the error and returns False instead of crashing
    # the login route (covers verify_password's except branch).
    assert result is False


@pytest.mark.unit
def test_verify_password_returns_false_for_empty_stored_hash():
    # Act — an empty stored hash (should never happen, but must not crash login).
    result = verify_password(password, "")

    # Assert — still a clean False, never an exception.
    assert result is False
