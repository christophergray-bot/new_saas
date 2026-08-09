"""Regression coverage for MGMT-0006 Backup & Restore System Health link."""
import os
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ManagementBackupHealthLinkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="fqc-mgmt-backup-health-"))
        cls.db_path = cls.tmpdir / "test.db"
        shutil.copy2(ROOT / "tests" / "fixtures" / "baseline.db", cls.db_path)
        os.chdir(ROOT)

        connection = sqlite3.connect(cls.db_path)
        try:
            cls.account_id = connection.execute(
                """INSERT INTO account_users
                   (email,password_hash,display_name,email_verified,
                    active,platform_role,auth_version)
                   VALUES('backup-health-owner@example.com','unused',
                          'Backup Health Owner',1,1,'application_owner',0)"""
            ).lastrowid
            connection.commit()
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

    def test_backup_center_system_health_link_targets_owner_health(self):
        client = self.app.test_client()
        with client.session_transaction() as session:
            session["account_user_id"] = int(self.account_id)
            session["auth_version"] = 0

        response = client.get("/maintenance/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            b'href="/developer/health">Open System Health</a>',
            response.data,
        )

        health = client.get("/developer/health")
        self.assertEqual(health.status_code, 200)


if __name__ == "__main__":
    unittest.main()
