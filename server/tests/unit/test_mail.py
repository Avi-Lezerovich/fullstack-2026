# -*- coding: utf-8 -*-
"""The SMTP backend, without an SMTP server.

The mail layer is the one part of the password-reset flow that talks to the
outside world, and the part nobody notices is broken until a real person cannot
get back into their account. It is also awkward to test honestly: a real relay
means credentials, a network, and a test that fails when someone else's service
is down.

So the seam is smtplib.SMTP itself. Replacing the class with a recorder pins the
conversation the code is supposed to have - connect, STARTTLS, log in, send -
which is exactly the sequence a misconfiguration gets wrong.
"""

from __future__ import annotations

import smtplib

import pytest

from app import mail


class FakeSMTP:
    """Stands in for smtplib.SMTP and writes down what was asked of it."""

    last: "FakeSMTP | None" = None

    def __init__(self, host, port, timeout=None):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.started_tls = False
        self.login_args = None
        self.sent = []
        self.closed = False
        FakeSMTP.last = self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.closed = True
        return False

    def starttls(self):
        self.started_tls = True

    def login(self, user, password):
        self.login_args = (user, password)

    def send_message(self, message):
        self.sent.append(message)


@pytest.fixture
def smtp_env(monkeypatch):
    """A fully configured SMTP backend. get_settings() re-reads the environment
    on every call by design, so setenv is all the wiring this needs."""
    monkeypatch.setenv("MAIL_BACKEND", "smtp")
    monkeypatch.setenv("MAIL_FROM", "LolSuit <court@lolsuit.test>")
    monkeypatch.setenv("SMTP_HOST", "smtp-relay.example.test")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USER", "relay-user")
    monkeypatch.setenv("SMTP_PASSWORD", "relay-secret")
    monkeypatch.setenv("SMTP_USE_TLS", "1")
    FakeSMTP.last = None
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)


@pytest.mark.unit
def test_smtp_backend_connects_upgrades_authenticates_and_sends(smtp_env):
    mail.send_mail(to="someone@example.test", subject="נושא", body="גוף ההודעה")

    smtp = FakeSMTP.last
    assert smtp is not None, "the smtp backend never opened a connection"
    assert (smtp.host, smtp.port) == ("smtp-relay.example.test", 587)
    assert smtp.started_tls, "STARTTLS is what makes port 587 safe to use"
    assert smtp.login_args == ("relay-user", "relay-secret")
    assert smtp.closed, "the connection must be closed even on the happy path"

    assert len(smtp.sent) == 1
    message = smtp.sent[0]
    assert message["To"] == "someone@example.test"
    # The sender comes from configuration, not from the caller.
    assert message["From"] == "LolSuit <court@lolsuit.test>"
    assert message["Subject"] == "נושא"
    assert "גוף ההודעה" in message.get_content()


@pytest.mark.unit
def test_no_credentials_means_no_login(monkeypatch, smtp_env):
    """An open relay - a local MTA, say - takes mail without authenticating.
    Calling login() with an empty user would fail the send outright."""
    monkeypatch.setenv("SMTP_USER", "")

    mail.send_mail(to="someone@example.test", subject="s", body="b")

    assert FakeSMTP.last.login_args is None
    assert len(FakeSMTP.last.sent) == 1


@pytest.mark.unit
def test_tls_off_skips_starttls(monkeypatch, smtp_env):
    monkeypatch.setenv("SMTP_USE_TLS", "0")

    mail.send_mail(to="someone@example.test", subject="s", body="b")

    assert FakeSMTP.last.started_tls is False


@pytest.mark.unit
def test_delivery_failure_is_swallowed(monkeypatch, smtp_env):
    """A dead relay must never turn into a 500 on the reset endpoint. The whole
    point of that endpoint is one identical answer for every address; an
    exception escaping here would make a registered address the only one that
    ever produced an error."""

    def explode(*args, **kwargs):
        raise smtplib.SMTPAuthenticationError(535, b"nope")

    monkeypatch.setattr(smtplib, "SMTP", explode)

    message = mail.send_mail(to="someone@example.test", subject="s", body="b")

    # Still returns the Message, so the caller can log what it tried to send.
    assert message.to == "someone@example.test"


@pytest.mark.unit
def test_console_backend_does_not_touch_smtp(monkeypatch, capsys):
    monkeypatch.setenv("MAIL_BACKEND", "console")
    FakeSMTP.last = None
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)

    mail.send_mail(to="someone@example.test", subject="s", body="the-reset-link")

    assert FakeSMTP.last is None
    # The link has to be readable in the log, or the dev default is useless.
    assert "the-reset-link" in capsys.readouterr().out


@pytest.mark.unit
def test_send_mail_async_delivers_off_the_calling_thread(smtp_env):
    """The reset endpoint uses this so a registered address and an unknown one
    take the same time to answer."""
    import threading

    caller = threading.current_thread().name
    seen = {}

    original = mail.send_mail

    def record(*args, **kwargs):
        seen["thread"] = threading.current_thread().name
        return original(*args, **kwargs)

    mail.send_mail = record
    try:
        mail.send_mail_async(to="someone@example.test", subject="s", body="b")
        for thread in threading.enumerate():
            if thread is not threading.current_thread():
                thread.join(timeout=5)
    finally:
        mail.send_mail = original

    assert seen.get("thread") not in (None, caller)
    assert FakeSMTP.last is not None and len(FakeSMTP.last.sent) == 1


@pytest.mark.unit
def test_reset_body_carries_the_link_and_the_ttl():
    body = mail.password_reset_body("דנה", "https://lolsuit.test/reset-password?token=abc", 30)

    assert "https://lolsuit.test/reset-password?token=abc" in body
    assert "30" in body
    assert "דנה" in body
