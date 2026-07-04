"""
A unit test — a pure function whose only input is one env var. Testing both
branches documents the security posture and covers both paths in utils.py.
"""



import pytest

from app.utils import session_cookie_flags


@pytest.mark.unit
def test_session_cookie_flags_default_is_lax_and_insecure(monkeypatch):
    # Arrange — no HTTPS configured (typical local dev).
    monkeypatch.delenv("FLASK_SESSION_SECURE", raising=False)

    # Act
    samesite, secure = session_cookie_flags()

    # Assert — SameSite=Lax works for same-origin dev; Secure is off (plain http).
    assert samesite == "Lax"
    assert secure is False


@pytest.mark.unit
def test_session_cookie_flags_secure_when_https_enabled(monkeypatch):
    # Arrange — behind HTTPS in production.
    monkeypatch.setenv("FLASK_SESSION_SECURE", "1")

    # Act
    samesite, secure = session_cookie_flags()

    # Assert — modern browsers require SameSite=None to be paired with Secure.
    assert samesite == "None"
    assert secure is True
