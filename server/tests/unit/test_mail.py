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


# --- the HTML alternative ---------------------------------------------------


@pytest.mark.unit
def test_html_message_is_alternative_with_the_seal_related_to_it():
    """Structure matters here, not just content. Plain text must be the FIRST
    alternative so a text-only client picks it, and the seal must be related to
    the HTML part rather than hanging off the top level - otherwise the
    cid: reference does not resolve and clients show it as a stray
    attachment."""
    html = mail.password_reset_html("דנה", "https://x.test/reset-password?token=t", 30)
    message = mail.Message(
        to="a@b.test", subject="s", body="plain", sender="LolSuit <c@d.test>", html=html
    )

    email = mail.build_email(message)

    assert email.get_content_type() == "multipart/alternative"
    text_part, related = email.get_payload()
    assert text_part.get_content_type() == "text/plain"
    assert "plain" in text_part.get_content()

    assert related.get_content_type() == "multipart/related"
    html_part, image = related.get_payload()
    assert html_part.get_content_type() == "text/html"
    assert image.get_content_type() == "image/png"
    assert image["Content-ID"] == f"<{mail.SEAL_CID}>"
    assert image.get_payload(decode=True)[:8] == b"\x89PNG\r\n\x1a\n"


@pytest.mark.unit
def test_plain_text_only_stays_a_single_part():
    email = mail.build_email(
        mail.Message(to="a@b.test", subject="s", body="plain", sender="c@d.test")
    )

    assert email.get_content_type() == "text/plain"
    assert not email.is_multipart()


@pytest.mark.unit
def test_reset_html_carries_the_link_in_both_the_button_and_the_copyable_url():
    url = "https://lolsuit.test/reset-password?token=abc-DEF_123"

    html = mail.password_reset_html("דנה", url, 45)

    assert f'href="{url}"' in html
    assert html.count(url) == 2, "the button and the copy-paste box"
    assert f"cid:{mail.SEAL_CID}" in html
    assert "45" in html
    assert 'dir="rtl"' in html


@pytest.mark.unit
def test_reset_html_escapes_the_name():
    """The display name comes from whatever the user typed at signup. Dropped
    into HTML unescaped it would be markup."""
    html = mail.password_reset_html('<script>alert(1)</script>', "https://x.test/r", 30)

    assert "<script>" not in html
    assert "&lt;script&gt;" in html


@pytest.mark.unit
def test_seal_survives_a_missing_asset(monkeypatch, smtp_env):
    """A missing PNG must cost the letterhead, not the email."""
    mail.seal_png.cache_clear()
    monkeypatch.setattr(mail, "ASSETS", mail.ASSETS / "does-not-exist")
    try:
        email = mail.build_email(
            mail.Message(
                to="a@b.test", subject="s", body="plain",
                sender="c@d.test", html="<p>hi</p>",
            )
        )
        # Still multipart/alternative with an HTML part - just no image.
        assert email.get_content_type() == "multipart/alternative"
        assert email.get_payload()[1].get_content_type() == "text/html"
    finally:
        mail.seal_png.cache_clear()


@pytest.mark.unit
def test_html_reaches_the_smtp_backend(smtp_env):
    mail.send_mail(to="a@b.test", subject="s", body="plain", html="<p>rich</p>")

    sent = FakeSMTP.last.sent[0]
    assert sent.get_content_type() == "multipart/alternative"


@pytest.mark.unit
def test_every_hebrew_cell_declares_its_own_direction():
    """Regression: the first version set dir="rtl" once, on <html>.

    Gmail discards the html/head/body wrapper and renders only what is inside
    it, so that single attribute survived every browser preview and vanished in
    Gmail - where the Hebrew then laid itself out left-aligned. Direction has to
    live on the cells, which are what actually gets delivered.
    """
    import re

    html = mail.password_reset_html("Avi", "https://x.test/r?token=t", 30)

    hebrew_cell_without_dir = re.compile(r"<td(?![^>]*\bdir=)[^>]*>\s*[֐-׿]")
    assert not hebrew_cell_without_dir.search(html)

    # And the same holds for what Gmail keeps: the body's contents alone.
    inner = re.search(r"<body[^>]*>(.*)</body>", html, re.S).group(1)
    assert 'dir="rtl"' in inner
    assert "text-align:right" in inner


@pytest.mark.unit
def test_the_seal_has_transparent_corners():
    """Regression: an opaque parchment square turned into a glaring white block
    on the recoloured card of a dark-mode client, which never inverts images.
    The disc is filled; the corners are not."""
    png = mail.seal_png()

    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    # Byte 25 of a PNG is the IHDR colour type; 6 is truecolour WITH alpha.
    assert png[25] == 6, "seal must keep an alpha channel"
