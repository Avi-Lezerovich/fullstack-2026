"""Outbound mail, with a backend chosen by configuration.

    console  print the message, including the reset link, to stdout (development)
    memory   collect messages in a list the tests can read
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
from dataclasses import dataclass, field
from email.message import EmailMessage

from .clock import now_utc
from .config import get_settings

log = logging.getLogger(__name__)


@dataclass
class Message:
    to: str
    subject: str
    body: str
    sender: str
    sent_at: str = field(default_factory=lambda: now_utc().isoformat(timespec="seconds"))


# The memory backend's store. Module-level so tests can inspect it without
# threading a mailer object through the application.
_outbox: list[Message] = []


def outbox() -> list[Message]:
    return _outbox


def clear_outbox() -> None:
    _outbox.clear()


def last_message() -> Message | None:
    return _outbox[-1] if _outbox else None


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


def _send_smtp(message: Message) -> None:  # pragma: no cover - needs a real server
    email = EmailMessage()
    email["To"] = message.to
    email["From"] = message.sender
    email["Subject"] = message.subject
    email.set_content(message.body)

    settings = get_settings()
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
        if settings.smtp_use_tls:
            smtp.starttls()
        if settings.smtp_user:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(email)


def send_mail(to: str, subject: str, body: str) -> Message:
    """Deliver a message through the configured backend.

    Returns the Message either way, so a caller can log what it tried to send
    even if delivery failed.
    """
    settings = get_settings()
    message = Message(to=to, subject=subject, body=body, sender=settings.mail_from)

    backend = settings.mail_backend
    try:
        if backend == "memory":
            _outbox.append(message)
        elif backend == "smtp":
            _send_smtp(message)
        else:
            _send_console(message)
    except Exception:  # pragma: no cover - delivery failures must not 500
        log.exception("could not deliver mail to %s", to)

    return message


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
