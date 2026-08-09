"""Tests for centralized hosted email configuration and SMTP delivery."""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from flask import Flask

from services.email_service import EmailConfigurationError, send_email


class EmailServiceTests(unittest.TestCase):
    def _app(self, **overrides):
        app = Flask(__name__)
        app.config.update({
            "MAIL_SERVER": "smtp.gmail.com",
            "MAIL_PORT": 587,
            "MAIL_USE_TLS": True,
            "MAIL_USERNAME": "owner@example.com",
            "MAIL_PASSWORD": "app-password",
            "MAIL_FROM": "Family Quest Center <owner@example.com>",
            "MAIL_TIMEOUT": 20,
        })
        app.config.update(overrides)
        return app

    def test_missing_password_is_rejected(self):
        app = self._app(MAIL_PASSWORD="")
        with app.app_context():
            with self.assertRaises(EmailConfigurationError):
                send_email(
                    recipients="owner@example.com",
                    subject="Test",
                    text_body="Test body",
                )

    @patch("services.email_service.smtplib.SMTP")
    def test_smtp_uses_tls_login_and_send_message(self, smtp_class):
        smtp = MagicMock()
        smtp_class.return_value.__enter__.return_value = smtp
        app = self._app()

        with app.app_context():
            send_email(
                recipients="owner@example.com",
                subject="Family Quest Center test",
                text_body="Test body",
            )

        smtp_class.assert_called_once_with("smtp.gmail.com", 587, timeout=20)
        smtp.starttls.assert_called_once()
        smtp.login.assert_called_once_with("owner@example.com", "app-password")
        smtp.send_message.assert_called_once()


if __name__ == "__main__":
    unittest.main(verbosity=2)
