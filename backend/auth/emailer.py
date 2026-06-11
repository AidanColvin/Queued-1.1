"""Transactional email (verification links, password resets).

Production sends through plain SMTP configured by the ``EMAIL_*`` settings.
When ``EMAIL_HOST`` is unset (local dev, CI), the message is logged to the
server console instead — the flow stays fully testable with no mail account.
Sending is best-effort: a mail failure is logged, never raised, so an SMTP
outage can't 500 an auth endpoint.
"""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from config import get_settings

logger = logging.getLogger("queued")


def send_email(to: str, subject: str, body: str) -> bool:
    """Send a plain-text email, or log it when SMTP is unconfigured.

    Returns:
        ``True`` if the message was handed to SMTP (or console-logged),
        ``False`` if an SMTP attempt failed.
    """
    settings = get_settings()
    if not settings.email_host:
        logger.info("EMAIL (console fallback) to=%s subject=%r\n%s", to, subject, body)
        return True

    msg = EmailMessage()
    msg["From"] = settings.email_from
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)

    try:
        with smtplib.SMTP(settings.email_host, settings.email_port, timeout=10) as smtp:
            smtp.starttls()
            if settings.email_username and settings.email_password:
                smtp.login(settings.email_username, settings.email_password)
            smtp.send_message(msg)
        return True
    except Exception:  # noqa: BLE001 — never let mail failures break auth flows
        logger.exception("Failed to send email to %s", to)
        return False
