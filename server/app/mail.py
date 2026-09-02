"""Outbound mail, with a backend chosen by configuration.

    console  print the message, including the reset link, to stdout (development)
    smtp     actually send

The console backend is what makes the password-reset flow demonstrable without
any mail infrastructure: the link appears in the server log, ready to paste
into a browser.

Nothing here raises. A failure to deliver mail must never turn into a 500 on
the request that triggered it, because the user-visible answer to "reset my
password" is deliberately the same whether or not the address exists.
"""

from __future__ import annotations

import logging
import smtplib
import sys
import threading
from dataclasses import dataclass, field
from email.message import EmailMessage
from functools import lru_cache
from html import escape
from pathlib import Path

from .clock import now_utc
from .config import get_settings

log = logging.getLogger(__name__)


ASSETS = Path(__file__).with_name("assets")

# The seal travels inside the message as an inline attachment rather than a
# link to the site. A remote <img> would be blocked by default in most mail
# clients, and would leak a read receipt - loading it tells the server the
# message was opened, which a password-reset email has no business reporting.
SEAL_CID = "lolsuit-seal"


@lru_cache(maxsize=None)
def seal_png() -> bytes:
    """The court seal, as PNG. Read once and kept.

    Two things about regenerating it from client/public/lolsuit-seal.svg:

    Use a BROWSER engine. librsvg/rsvg-convert silently drops <textPath> and
    hands back a seal with both of its arcs of text missing.

    Keep the corners TRANSPARENT and fill only the disc (add a parchment
    circle at r=158, just inside the outer ring). Dark-mode clients invert the
    card behind the image but never the image itself, so an opaque parchment
    square turns into a glaring white block on a dark background; a medallion
    with transparent corners sits correctly on either.
    """
    try:
        return (ASSETS / "lolsuit-seal.png").read_bytes()
    except OSError:
        log.warning("court seal asset missing; sending mail without it")
        return b""


@dataclass
class Message:
    to: str
    subject: str
    body: str
    sender: str
    html: str | None = None
    sent_at: str = field(default_factory=lambda: now_utc().isoformat(timespec="seconds"))


def _send_console(message: Message) -> None:  # pragma: no cover - dev output only
    print(
        "\n"
        "========================= LolSuit mail =========================\n"
        f"To:      {message.to}\n"
        f"From:    {message.sender}\n"
        f"Subject: {message.subject}\n"
        "----------------------------------------------------------------\n"
        f"{message.body}\n"
        "================================================================\n",
        file=sys.stdout,
        flush=True,
    )


def build_email(message: Message) -> EmailMessage:
    """Assemble the MIME message.

    Plain text is the real body and always comes first: it is what a client
    that refuses HTML shows, and it is the version that still contains a
    usable reset link when every image and style has been stripped. The HTML
    alternative is decoration on top of it, never a replacement.
    """
    email = EmailMessage()
    email["To"] = message.to
    email["From"] = message.sender
    email["Subject"] = message.subject
    email.set_content(message.body)

    if message.html:
        email.add_alternative(message.html, subtype="html")
        seal = seal_png()
        if seal:
            # The HTML part becomes multipart/related so the <img cid:> in it
            # resolves against this attachment.
            email.get_payload()[1].add_related(
                seal, maintype="image", subtype="png", cid=f"<{SEAL_CID}>"
            )
    return email


def _send_smtp(message: Message) -> None:  # pragma: no cover - needs a real server
    email = build_email(message)

    settings = get_settings()
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
        if settings.smtp_use_tls:
            smtp.starttls()
        if settings.smtp_user:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(email)


def send_mail(to: str, subject: str, body: str, html: str | None = None) -> Message:
    """Deliver a message through the configured backend.

    Returns the Message either way, so a caller can log what it tried to send
    even if delivery failed.
    """
    settings = get_settings()
    message = Message(
        to=to, subject=subject, body=body, sender=settings.mail_from, html=html
    )

    try:
        if settings.mail_backend == "smtp":
            _send_smtp(message)
        else:
            _send_console(message)
    except Exception:  # pragma: no cover - delivery failures must not 500
        log.exception("could not deliver mail to %s", to)
    else:
        # Worth a line even on success: without it the log is silent when mail
        # works and silent-plus-a-traceback when it does not, which makes "did
        # that reset link ever go out?" unanswerable after the fact.
        log.info("mail delivered to %s via %s", to, settings.mail_backend)

    return message


def send_mail_async(to: str, subject: str, body: str, html: str | None = None) -> None:
    """Hand delivery to a background thread and return immediately.

    The password-reset endpoint answers identically for a registered address
    and an unknown one - that is the whole point of it. Sending inline would
    undo that: an unknown address returns at once while a known one waits out
    an SMTP round trip, and the response *time* leaks what the response body
    refuses to. Off the request thread, both answer at the same speed.

    A bare daemon thread is enough. send_mail swallows every exception, and it
    touches no Flask request context - get_settings() reads the environment
    afresh on each call - so there is nothing here to carry across.
    """
    threading.Thread(
        target=send_mail, args=(to, subject, body, html), daemon=True
    ).start()


# --- the court's stationery -------------------------------------------------
#
# Email HTML is not web HTML. Tables carry the layout because Outlook has no
# flexbox, every style is inline because Gmail strips <style> blocks, and the
# button is a table cell with a background rather than a styled <a>, because
# Outlook drops padding on inline elements.
#
# Direction is set on EVERY cell rather than once on <html>, because Gmail
# throws away the html/head/body wrapper and keeps only what is inside it -
# so a single dir="rtl" up there survives in a browser preview and vanishes in
# the one client that matters most. text-align goes with it: dir alone orders
# the characters, it does not decide which edge a short line sits against.
#
# Nothing here is load-bearing. Images off, CSS stripped, HTML refused - the
# plain-text part still carries the link, and that is the part that matters.

PURPLE = "#3C3489"   # Court Purple, the brand colour
GOLD = "#B8860B"     # the rule under the site's AppBar
PARCHMENT = "#FAF6E9"
INK = "#1A1530"
MUTED = "#5A5470"
EDGE = "#DED4B4"
SERIF = "Georgia, 'Times New Roman', 'David', serif"


def password_reset_html(name: str, reset_url: str, ttl_minutes: int) -> str:
    """The same message as password_reset_body, dressed in the court's seal."""
    safe_name = escape(name)
    safe_url = escape(reset_url, quote=True)

    return f"""<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width">
<meta name="color-scheme" content="light">
<meta name="supported-color-schemes" content="light">
</head>
<body dir="rtl" style="margin:0;padding:0;background-color:#E8E0C8;">
<table role="presentation" dir="rtl" width="100%" cellpadding="0" cellspacing="0" border="0"
       style="background-color:#E8E0C8;">
  <tr><td align="center" style="padding:24px 12px;">

    <table role="presentation" dir="rtl" width="100%" cellpadding="0" cellspacing="0" border="0"
           style="max-width:560px;background-color:{PARCHMENT};border:1px solid {EDGE};">

      <tr><td style="background-color:{PURPLE};height:8px;line-height:8px;font-size:0;">&nbsp;</td></tr>
      <tr><td style="background-color:{GOLD};height:3px;line-height:3px;font-size:0;">&nbsp;</td></tr>

      <tr><td align="center" style="padding:32px 24px 4px 24px;">
        <img src="cid:{SEAL_CID}" width="120" height="120"
             alt="חותמת בית המשפט לתביעות מצחיקות"
             style="display:block;border:0;outline:none;text-decoration:none;">
      </td></tr>

      <tr><td align="center" dir="rtl" style="padding:8px 24px 0 24px;font-family:{SERIF};
               font-size:22px;font-weight:bold;color:{PURPLE};text-align:center;">
        איפוס סיסמה
      </td></tr>

      <tr><td align="center" dir="rtl" style="padding:20px 32px 0 32px;font-family:{SERIF};
               font-size:16px;line-height:26px;color:{INK};text-align:center;">
        שלום {safe_name},
        <br><br>
        התקבלה בקשה לאיפוס הסיסמה שלך ב-LolSuit.
      </td></tr>

      <tr><td align="center" style="padding:26px 32px 6px 32px;">
        <table role="presentation" cellpadding="0" cellspacing="0" border="0">
          <tr><td align="center" bgcolor="{PURPLE}" style="border-radius:4px;">
            <a href="{safe_url}" style="display:inline-block;padding:14px 34px;
               font-family:{SERIF};font-size:16px;font-weight:bold;
               color:{PARCHMENT};text-decoration:none;border-radius:4px;">
              בחירת סיסמה חדשה
            </a>
          </td></tr>
        </table>
      </td></tr>

      <tr><td align="right" dir="rtl" style="padding:18px 32px 0 32px;font-family:{SERIF};
               font-size:13px;line-height:20px;color:{MUTED};text-align:right;">
        אם הכפתור לא עובד, אפשר להעתיק את הכתובת הזו לדפדפן:
      </td></tr>

      <tr><td style="padding:8px 32px 0 32px;">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
          <tr><td dir="ltr" align="left"
                  style="background-color:#F3EDDA;border:1px solid {EDGE};padding:10px 12px;
                         direction:ltr;text-align:left;font-family:Consolas,Menlo,monospace;
                         font-size:12px;line-height:18px;color:{PURPLE};word-break:break-all;">{safe_url}</td></tr>
        </table>
      </td></tr>

      <tr><td style="padding:22px 32px 0 32px;">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
          <tr><td style="border-top:1px solid {EDGE};height:1px;line-height:1px;font-size:0;">&nbsp;</td></tr>
        </table>
      </td></tr>

      <tr><td align="right" dir="rtl" style="padding:16px 32px 0 32px;font-family:{SERIF};
               font-size:14px;line-height:23px;color:{MUTED};text-align:right;">
        הקישור תקף למשך {ttl_minutes} דקות וניתן לשימוש חד-פעמי בלבד.
        <br>
        לאחר איפוס הסיסמה תתבצע יציאה מכל המכשירים המחוברים.
        <br><br>
        אם לא ביקשת לאפס סיסמה, אפשר להתעלם מההודעה הזו - לא בוצע שום שינוי.
      </td></tr>

      <tr><td align="center" dir="rtl" style="padding:26px 32px 30px 32px;font-family:{SERIF};
               font-size:13px;line-height:20px;color:{PURPLE};text-align:center;">
        בברכה,
        <br>
        <strong>מזכירות בית המשפט לתביעות מצחיקות</strong>
      </td></tr>

    </table>

  </td></tr>
</table>
</body>
</html>"""


def password_reset_body(name: str, reset_url: str, ttl_minutes: int) -> str:
    return (
        f"שלום {name},\n\n"
        "התקבלה בקשה לאיפוס הסיסמה שלך ב-LolSuit.\n"
        "כדי לבחור סיסמה חדשה, היכנס/י לקישור הבא:\n\n"
        f"{reset_url}\n\n"
        f"הקישור תקף למשך {ttl_minutes} דקות וניתן לשימוש חד-פעמי בלבד.\n"
        "לאחר איפוס הסיסמה תתבצע יציאה מכל המכשירים המחוברים.\n\n"
        "אם לא ביקשת לאפס סיסמה, אפשר להתעלם מההודעה הזו - לא בוצע שום שינוי.\n\n"
        "בברכה,\n"
        "מזכירות בית המשפט לתביעות מצחיקות\n"
    )
