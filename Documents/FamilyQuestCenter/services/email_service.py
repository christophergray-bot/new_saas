"""Centralized outbound email delivery for Family Quest Center.

Credentials are supplied through environment-backed Flask configuration and
must never be written to source control, application logs, or audit details.
"""
from __future__ import annotations

import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import parseaddr
from typing import Iterable

from flask import current_app


class EmailConfigurationError(RuntimeError):
    """Raised when required SMTP configuration is incomplete or invalid."""


class EmailDeliveryError(RuntimeError):
    """Raised when the configured SMTP server rejects or cannot deliver mail."""


@dataclass(frozen=True)
class EmailSettings:
    server: str
    port: int
    use_tls: bool
    username: str
    password: str
    sender: str
    timeout: int


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def get_email_settings() -> EmailSettings:
    """Read and validate SMTP settings from the active Flask application."""
    config = current_app.config
    settings = EmailSettings(
        server=str(config.get("MAIL_SERVER", "")).strip(),
        port=int(config.get("MAIL_PORT", 587)),
        use_tls=_as_bool(config.get("MAIL_USE_TLS", True)),
        username=str(config.get("MAIL_USERNAME", "")).strip(),
        password=str(config.get("MAIL_PASSWORD", "")).strip(),
        sender=str(config.get("MAIL_FROM", "")).strip(),
        timeout=int(config.get("MAIL_TIMEOUT", 20)),
    )

    missing = [
        name
        for name, value in (
            ("MAIL_SERVER", settings.server),
            ("MAIL_USERNAME", settings.username),
            ("MAIL_PASSWORD", settings.password),
            ("MAIL_FROM", settings.sender),
        )
        if not value
    ]
    if missing:
        raise EmailConfigurationError(
            "Email is not fully configured. Missing: " + ", ".join(missing)
        )

    _, sender_address = parseaddr(settings.sender)
    if not sender_address or "@" not in sender_address:
        raise EmailConfigurationError("MAIL_FROM must contain a valid email address.")
    if settings.port < 1 or settings.port > 65535:
        raise EmailConfigurationError("MAIL_PORT must be between 1 and 65535.")
    return settings


def email_configuration_status() -> dict[str, object]:
    """Return a secret-free configuration summary for installation-owner UI."""
    config = current_app.config
    required = ("MAIL_SERVER", "MAIL_USERNAME", "MAIL_PASSWORD", "MAIL_FROM")
    missing = [name for name in required if not str(config.get(name, "")).strip()]
    return {
        "configured": not missing,
        "missing": missing,
        "server": str(config.get("MAIL_SERVER", "")).strip() or "Not configured",
        "port": int(config.get("MAIL_PORT", 587)),
        "use_tls": _as_bool(config.get("MAIL_USE_TLS", True)),
        "username": str(config.get("MAIL_USERNAME", "")).strip() or "Not configured",
        "sender": str(config.get("MAIL_FROM", "")).strip() or "Not configured",
        "app_url": str(config.get("APP_URL", "")).strip() or "Not configured",
    }


def send_email(
    *,
    recipients: str | Iterable[str],
    subject: str,
    text_body: str,
    html_body: str | None = None,
) -> None:
    """Send one message through the configured SMTP service.

    The password and complete SMTP exception details are deliberately excluded
    from raised messages so they cannot be exposed through the UI or audit log.
    """
    settings = get_email_settings()
    recipient_list = [recipients] if isinstance(recipients, str) else list(recipients)
    recipient_list = [str(item).strip() for item in recipient_list if str(item).strip()]
    if not recipient_list:
        raise ValueError("At least one recipient is required.")

    message = EmailMessage()
    message["Subject"] = subject.strip()
    message["From"] = settings.sender
    message["To"] = ", ".join(recipient_list)
    message.set_content(text_body)
    if html_body:
        message.add_alternative(html_body, subtype="html")

    try:
        with smtplib.SMTP(settings.server, settings.port, timeout=settings.timeout) as smtp:
            smtp.ehlo()
            if settings.use_tls:
                smtp.starttls(context=ssl.create_default_context())
                smtp.ehlo()
            smtp.login(settings.username, settings.password)
            smtp.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        current_app.logger.warning(
            "Outbound email delivery failed through configured SMTP service: %s",
            type(exc).__name__,
        )
        raise EmailDeliveryError(
            "The email could not be delivered. Verify the Railway mail settings and Google App Password."
        ) from exc
