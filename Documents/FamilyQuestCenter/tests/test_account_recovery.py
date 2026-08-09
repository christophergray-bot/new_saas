"""Regression tests for hosted password recovery and Parent Two invitations."""
from __future__ import annotations

import re
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class AccountRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="fqc-account-recovery-"))
        cls.db_path = cls.tmpdir / "recovery.db"
        from app import create_app
        cls.app = create_app({
            "TESTING": True,
            "ENVIRONMENT": "development",
            "IS_PRODUCTION": False,
            "SECRET_KEY": "test-secret-key-that-is-long-enough-12345",
            "DATABASE_PATH": cls.db_path,
            "BACKUP_DIRECTORY": cls.tmpdir / "backups",
            "SESSION_COOKIE_SECURE": False,
            "REGISTRATION_MODE": "local",
            "APP_URL": "https://example.test",
            "MAIL_SERVER": "smtp.example.test",
            "MAIL_USERNAME": "sender@example.test",
            "MAIL_PASSWORD": "test-password",
            "MAIL_FROM": "sender@example.test",
        })

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def setUp(self):
        db = sqlite3.connect(self.db_path)
        db.execute("PRAGMA foreign_keys=OFF")
        for table in [row[0] for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )]:
            db.execute(f'DELETE FROM "{table}"')
        db.commit()
        db.close()

        from services.multifamily_foundation import ensure_multifamily_foundation
        from services.default_achievements import ensure_core_achievements
        from services.onboarding import ensure_onboarding_schema
        ensure_multifamily_foundation(self.db_path)
        ensure_core_achievements(self.db_path)
        ensure_onboarding_schema(self.db_path)

        self.client = self.app.test_client()
        self._setup_application_owner()
        self._register_owner()

    def _csrf_from(self, path: str) -> str:
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        match = re.search(rb'name="csrf_token" value="([^"]+)"', response.data)
        self.assertIsNotNone(match)
        return match.group(1).decode()

    def _setup_application_owner(self):
        token = self._csrf_from("/account/setup-owner")
        response = self.client.post(
            "/account/setup-owner",
            data={
                "csrf_token": token,
                "display_name": "Application Owner",
                "email": "platform-owner@example.com",
                "password": "PlatformOwner123",
                "confirm_password": "PlatformOwner123",
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        # Family registration is a separate public/customer workflow.
        with self.client.session_transaction() as browser_session:
            browser_session.clear()

    def _register_owner(self):
        token = self._csrf_from("/account/register")
        response = self.client.post(
            "/account/register",
            data={
                "csrf_token": token,
                "family_name": "Recovery Family",
                "display_name": "Parent One",
                "email": "owner@example.com",
                "password": "OwnerPassword123",
                "confirm_password": "OwnerPassword123",
                "starter_experience": "empty",
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)


    def test_application_url_ignores_accidental_login_path(self):
        from services.account_tokens import application_url
        with self.app.app_context():
            original = self.app.config["APP_URL"]
            self.app.config["APP_URL"] = "https://example.test/account/login"
            try:
                self.assertEqual(
                    application_url("/account/reset-password/example-token"),
                    "https://example.test/account/reset-password/example-token",
                )
                self.assertEqual(
                    application_url("/parent/management/invitation/example-token"),
                    "https://example.test/parent/management/invitation/example-token",
                )
            finally:
                self.app.config["APP_URL"] = original

    def test_unknown_email_uses_same_public_response(self):
        self.client.post("/account/logout", data={"csrf_token": self._csrf_from("/account/profile")})
        token = self._csrf_from("/account/forgot-password")
        with patch("routes.account.send_email") as mocked_send:
            response = self.client.post(
                "/account/forgot-password",
                data={"csrf_token": token, "email": "unknown@example.com"},
                follow_redirects=True,
            )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"If an active account matches", response.data)
        mocked_send.assert_not_called()

    def test_password_reset_token_is_one_time_and_changes_password(self):
        self.client.get("/account/logout")
        token = self._csrf_from("/account/forgot-password")
        captured = {}
        def capture_email(**kwargs):
            captured.update(kwargs)
        with patch("routes.account.send_email", side_effect=capture_email):
            self.client.post(
                "/account/forgot-password",
                data={"csrf_token": token, "email": "owner@example.com"},
            )
        match = re.search(r"/account/reset-password/([^\s<]+)", captured["text_body"])
        self.assertIsNotNone(match)
        raw_token = match.group(1)
        reset_path = f"/account/reset-password/{raw_token}"
        csrf = self._csrf_from(reset_path)
        response = self.client.post(
            reset_path,
            data={"csrf_token": csrf, "password": "NewPassword123", "confirm_password": "NewPassword123"},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        reused = self.client.get(reset_path, follow_redirects=True)
        self.assertIn(b"invalid, expired, or has already been used", reused.data)

    def test_parent_invitation_email_and_acceptance(self):
        # Complete PIN setup so Parent Management is reachable.
        token = self._csrf_from("/parent/setup-pin")
        self.client.post(
            "/parent/setup-pin",
            data={"csrf_token": token, "pin": "1234", "confirm_pin": "1234"},
        )
        token = self._csrf_from("/parent/management/")
        captured = {}
        with patch("routes.parent_management.send_email", side_effect=lambda **kwargs: captured.update(kwargs)):
            response = self.client.post(
                "/parent/management/invite",
                data={"csrf_token": token, "email": "parenttwo@example.com"},
                follow_redirects=False,
            )
        self.assertEqual(response.status_code, 302)
        match = re.search(r"/parent/management/invitation/([^\s<]+)", captured["text_body"])
        self.assertIsNotNone(match)
        invite_path = f"/parent/management/invitation/{match.group(1)}"
        self.client.get("/account/logout")
        csrf = self._csrf_from(invite_path)
        response = self.client.post(
            invite_path,
            data={
                "csrf_token": csrf,
                "display_name": "Parent Two",
                "password": "ParentTwo123",
                "confirm_password": "ParentTwo123",
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        db = sqlite3.connect(self.db_path)
        row = db.execute(
            """SELECT fm.role FROM family_memberships fm
               JOIN account_users au ON au.id=fm.account_user_id
               WHERE au.email='parenttwo@example.com' AND fm.active=1"""
        ).fetchone()
        db.close()
        self.assertEqual(row[0], "parent")


    def test_parent_invitation_allows_placeholder_account_to_create_password(self):
        # Simulate a legacy invitation workflow that created the account row
        # before Parent Two had selected a password.
        db = sqlite3.connect(self.db_path)
        db.execute(
            """INSERT INTO account_users
                (email,password_hash,display_name,email_verified,active)
                VALUES ('placeholder-parent@example.com','INVITED','Pending Parent',0,1)"""
        )
        db.commit()
        db.close()

        token = self._csrf_from("/parent/setup-pin")
        self.client.post(
            "/parent/setup-pin",
            data={"csrf_token": token, "pin": "1234", "confirm_pin": "1234"},
        )
        token = self._csrf_from("/parent/management/")
        captured = {}
        with patch("routes.parent_management.send_email", side_effect=lambda **kwargs: captured.update(kwargs)):
            response = self.client.post(
                "/parent/management/invite",
                data={"csrf_token": token, "email": "placeholder-parent@example.com"},
                follow_redirects=False,
            )
        self.assertEqual(response.status_code, 302)
        match = re.search(r"/parent/management/invitation/([^\s<]+)", captured["text_body"])
        self.assertIsNotNone(match)
        invite_path = f"/parent/management/invitation/{match.group(1)}"

        self.client.get("/account/logout")
        invite_page = self.client.get(invite_path)
        self.assertEqual(invite_page.status_code, 200)
        self.assertIn(b"Create Your Parent Account", invite_page.data)
        self.assertIn(b"confirm_password", invite_page.data)

        csrf = self._csrf_from(invite_path)
        response = self.client.post(
            invite_path,
            data={
                "csrf_token": csrf,
                "display_name": "Parent Two",
                "password": "ParentTwo123",
                "confirm_password": "ParentTwo123",
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)

        db = sqlite3.connect(self.db_path)
        row = db.execute(
            "SELECT password_hash,email_verified,active FROM account_users WHERE email='placeholder-parent@example.com'"
        ).fetchone()
        db.close()
        self.assertTrue(row[0].startswith(("scrypt:", "pbkdf2:")))
        self.assertEqual(row[1:], (1, 1))

    def test_cancel_and_reinvite_same_email(self):
        token = self._csrf_from("/parent/setup-pin")
        self.client.post(
            "/parent/setup-pin",
            data={"csrf_token": token, "pin": "1234", "confirm_pin": "1234"},
        )

        token = self._csrf_from("/parent/management/")
        with patch("routes.parent_management.send_email"):
            first = self.client.post(
                "/parent/management/invite",
                data={"csrf_token": token, "email": "repeat-parent@example.com"},
                follow_redirects=False,
            )
        self.assertEqual(first.status_code, 302)

        token = self._csrf_from("/parent/management/")
        cancelled = self.client.post(
            "/parent/management/invitation/cancel",
            data={"csrf_token": token},
            follow_redirects=False,
        )
        self.assertEqual(cancelled.status_code, 302)

        token = self._csrf_from("/parent/management/")
        captured = {}
        with patch("routes.parent_management.send_email", side_effect=lambda **kwargs: captured.update(kwargs)):
            second = self.client.post(
                "/parent/management/invite",
                data={"csrf_token": token, "email": "repeat-parent@example.com"},
                follow_redirects=False,
            )
        self.assertEqual(second.status_code, 302)
        self.assertIn("repeat-parent@example.com", captured["recipients"])

        db = sqlite3.connect(self.db_path)
        rows = db.execute(
            """SELECT status, COUNT(*) FROM parent_invitations
               WHERE email='repeat-parent@example.com'
               GROUP BY status"""
        ).fetchall()
        db.close()
        counts = dict(rows)
        self.assertEqual(counts.get("cancelled"), 1)
        self.assertEqual(counts.get("pending"), 1)

    def test_orphaned_hashed_account_is_treated_as_first_time_parent(self):
        from werkzeug.security import generate_password_hash

        db = sqlite3.connect(self.db_path)
        db.execute(
            """INSERT INTO account_users
               (email,password_hash,display_name,email_verified,active)
               VALUES (?,?,?,?,1)""",
            (
                "orphan-parent@example.com",
                generate_password_hash("TemporaryInvitePassword123"),
                "Pending Parent",
                0,
            ),
        )
        db.commit()
        db.close()

        token = self._csrf_from("/parent/setup-pin")
        self.client.post(
            "/parent/setup-pin",
            data={"csrf_token": token, "pin": "1234", "confirm_pin": "1234"},
        )
        token = self._csrf_from("/parent/management/")
        captured = {}
        with patch("routes.parent_management.send_email", side_effect=lambda **kwargs: captured.update(kwargs)):
            response = self.client.post(
                "/parent/management/invite",
                data={"csrf_token": token, "email": "orphan-parent@example.com"},
                follow_redirects=False,
            )
        self.assertEqual(response.status_code, 302)
        match = re.search(r"/parent/management/invitation/([^\s<]+)", captured["text_body"])
        self.assertIsNotNone(match)

        self.client.get("/account/logout")
        invite_page = self.client.get(f"/parent/management/invitation/{match.group(1)}")
        self.assertEqual(invite_page.status_code, 200)
        self.assertIn(b"Create Your Parent Account", invite_page.data)
        self.assertIn(b"confirm_password", invite_page.data)


if __name__ == "__main__":
    unittest.main(verbosity=2)
