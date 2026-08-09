"""Regression coverage for MGMT-0002 system-wide Release Diagnostics."""
import os
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ManagementReleaseDiagnosticsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="fqc-mgmt-diagnostics-"))
        cls.db_path = cls.tmpdir / "test.db"
        shutil.copy2(ROOT / "tests" / "fixtures" / "baseline.db", cls.db_path)
        os.chdir(ROOT)

        connection = sqlite3.connect(cls.db_path)
        try:
            account_id = connection.execute(
                """INSERT INTO account_users
                   (email,password_hash,display_name,email_verified,
                    active,platform_role,auth_version)
                   VALUES(?, 'unused', ?, 1, 1, 'application_owner', 0)""",
                ("diagnostics-test-owner@example.com", "Diagnostics Test Owner"),
            ).lastrowid
            connection.commit()
            cls.account_id = int(account_id)
            cls.auth_version = 0
        finally:
            connection.close()

        from app import create_app

        cls.app = create_app({
            "TESTING": True,
            "ENVIRONMENT": "development",
            "IS_PRODUCTION": False,
            "SECRET_KEY": "test-secret-key-that-is-long-enough-12345",
            "DATABASE_PATH": cls.db_path,
            "SESSION_COOKIE_SECURE": False,
        })

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def test_owner_without_family_context_can_open_release_diagnostics(self):
        client = self.app.test_client()
        with client.session_transaction() as session:
            session["account_user_id"] = self.account_id
            session["auth_version"] = self.auth_version

        response = client.get("/developer/diagnostics")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Release Diagnostics", response.data)
        self.assertIn(b"SYSTEM-WIDE", response.data)
        self.assertIn(b"Active families:", response.data)
        self.assertNotIn(b"Family ID:", response.data)

    def test_parent_cannot_open_release_diagnostics(self):
        connection = sqlite3.connect(self.db_path)
        try:
            family_id = connection.execute(
                "SELECT id FROM families WHERE status='active' ORDER BY id LIMIT 1"
            ).fetchone()[0]
            account_id = connection.execute(
                """INSERT INTO account_users
                   (email,password_hash,display_name,email_verified,
                    active,platform_role,auth_version)
                   VALUES('diagnostics-parent@example.com','unused',
                          'Diagnostics Parent',1,1,'none',0)"""
            ).lastrowid
            connection.execute(
                """INSERT INTO family_memberships
                   (family_id,account_user_id,role,active)
                   VALUES(?,?, 'parent',1)""",
                (family_id, account_id),
            )
            connection.commit()
        finally:
            connection.close()

        client = self.app.test_client()
        with client.session_transaction() as session:
            session["account_user_id"] = int(account_id)
            session["family_id"] = int(family_id)
            session["auth_version"] = 0
            session["parent_authenticated"] = True

        response = client.get("/developer/diagnostics")
        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
