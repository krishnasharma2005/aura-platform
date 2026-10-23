"""Sending an email — the one place the product does it.

Provider-neutral on purpose: any SMTP service works (Brevo, Resend, Postmark,
Amazon SES, Gmail with an app password), so choosing one later is a settings
change, not a code change. Standard library only — no new dependency.

With `SMTP_HOST` unset nothing is sent. In development the message is logged,
which is how you follow a password-reset link on your own machine. In
production it is *not* logged: a reset link in a log file is an account takeover
for anyone who can read the log, so production just warns that email isn't set up.
"""

import asyncio
import smtplib
import ssl
from abc import ABC, abstractmethod
from email.message import EmailMessage

from src.core.config import get_settings
from src.core.logging import get_logger

logger = get_logger(__name__)

_TIMEOUT_SECONDS = 15


class Mailer(ABC):
    @abstractmethod
    async def send(self, to: str, subject: str, body: str) -> None: ...


class ConsoleMailer(Mailer):
    """Used when no SMTP server is configured."""

    async def send(self, to: str, subject: str, body: str) -> None:
        if get_settings().ENV == "production":
            logger.warning(
                "email_not_configured",
                extra={"extra_fields": {"to_domain": to.rsplit("@", 1)[-1], "subject": subject}},
            )
            return
        logger.info(
            "email_not_sent_logged_instead",
            extra={"extra_fields": {"to": to, "subject": subject, "body": body}},
        )


class SMTPMailer(Mailer):
    def __init__(self) -> None:
        self._settings = get_settings()

    def _build(self, to: str, subject: str, body: str) -> EmailMessage:
        message = EmailMessage()
        message["From"] = self._settings.EMAIL_FROM
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)
        return message

    def _send_blocking(self, message: EmailMessage) -> None:
        settings = self._settings
        context = ssl.create_default_context()
        if settings.SMTP_USE_SSL:
            server: smtplib.SMTP = smtplib.SMTP_SSL(
                settings.SMTP_HOST, settings.SMTP_PORT, timeout=_TIMEOUT_SECONDS, context=context
            )
        else:
            server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=_TIMEOUT_SECONDS)
        with server:
            if not settings.SMTP_USE_SSL:
                server.starttls(context=context)  # never send credentials or links in the clear
            if settings.SMTP_USERNAME:
                server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD or "")
            server.send_message(message)

    async def send(self, to: str, subject: str, body: str) -> None:
        # smtplib is blocking; keep it off the event loop so a slow mail server
        # can't stall every other request.
        await asyncio.to_thread(self._send_blocking, self._build(to, subject, body))


def get_mailer() -> Mailer:
    return SMTPMailer() if get_settings().SMTP_HOST else ConsoleMailer()


async def send_email_safely(to: str, subject: str, body: str) -> None:
    """For background use: a mail failure is logged and swallowed. Callers like
    "forgot password" return the same answer whether or not an email went out, so
    there's no one to show an error to — and an exception here would otherwise
    surface as a failed request after the response was already sent."""
    try:
        await get_mailer().send(to, subject, body)
    except Exception as exc:
        logger.error(
            "email_send_failed",
            exc_info=exc,
            extra={"extra_fields": {"to_domain": to.rsplit("@", 1)[-1], "subject": subject}},
        )
