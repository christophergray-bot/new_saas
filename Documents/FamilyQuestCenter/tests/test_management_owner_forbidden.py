"""Regression coverage for MGMT-0005 authenticated Owner authorization."""
import os
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ManagementOwnerForbiddenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="fqc-mgmt-owner-forbidden-"))
        cls.db_path = cls.tmpdir / "test.db"
        shutil.copy2(ROOT / "tests" / "fixtures" / "baseline.db", cls.db_path)
        os.chdir(ROOT)

        connection = sqlite3.connect(cls.db_path)
        try:
            cls.owner_id = connection.execute(
                """INSERT INTO account_users
                   (email,password_hash,display_name,email_verified,active,
                    platform_role,auth_version)
                   VALUES('forbidden-owner@example.com','unused',
                          'Forbidden Test Owner',1,1,'application_owner',0)"""
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

    def _owner_client(self):
        client = self.app.test_client()
        with client.session_transaction() as session:
            session["account_user_id"] = int(self.owner_id)
            session["auth_version"] = 0
        return client

    def test_authenticated_owner_without_family_gets_403_on_parent_route(self):
        response = self._owner_client().get("/parent/", follow_redirects=False)
        self.assertEqual(response.status_code, 403)
        self.assertNotIn("/account/login", response.headers.get("Location", ""))

    def test_authenticated_owner_without_family_gets_403_on_family_route(self):
        response = self._owner_client().get("/family", follow_redirects=False)
        self.assertEqual(response.status_code, 403)
        self.assertNotIn("/account/login", response.headers.get("Location", ""))

    def test_unauthenticated_user_still_redirects_to_login(self):
        response = self.app.test_client().get("/parent/", follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/account/login", response.headers.get("Location", ""))


if __name__ == "__main__":
    unittest.main()
