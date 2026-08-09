"""Regression tests for Parent One and Parent Two security boundaries."""
from __future__ import annotations

import os
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

from werkzeug.security import generate_password_hash

ROOT = Path(__file__).resolve().parents[1]

from tests.fixture_utils import ensure_primary_family_fixture


class ParentRoleControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="fqc-parent-roles-"))
        cls.db_path = cls.tmpdir / "roles.db"
        shutil.copy2(ROOT / "tests" / "fixtures" / "baseline.db", cls.db_path)
        os.chdir(ROOT)

        from app import create_app

        cls.app = create_app({
            "TESTING": True,
            "ENVIRONMENT": "development",
            "IS_PRODUCTION": False,
            "SECRET_KEY": "test-secret-key-that-is-long-enough-12345",
            "DATABASE_PATH": cls.db_path,
            "BACKUP_DIRECTORY": cls.tmpdir / "backups",
            "SESSION_COOKIE_SECURE": False,
        })

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def setUp(self):
        source = sqlite3.connect(ROOT / "tests" / "fixtures" / "baseline.db")
        destination = sqlite3.connect(self.db_path)
        try:
            source.backup(destination)
        finally:
            destination.close()
            source.close()
        ensure_primary_family_fixture(self.db_path)

        db = sqlite3.connect(self.db_path)
        try:
            db.execute(
                """INSERT INTO account_users
                   (email,password_hash,display_name,email_verified,active,auth_version)
                   VALUES (?,?,?,?,1,0)""",
                (
                    "parent-two-role-test@example.com",
                    generate_password_hash("ParentTwoPassword123"),
                    "Parent Two Test",
                    1,
                ),
            )
            self.parent_two_id = db.execute(
                "SELECT id FROM account_users WHERE email=?",
                ("parent-two-role-test@example.com",),
            ).fetchone()[0]
            db.execute(
                """INSERT INTO family_memberships
                   (family_id,account_user_id,role,active)
                   VALUES (1,?,'parent',1)""",
                (self.parent_two_id,),
            )
            db.commit()
        finally:
            db.close()

    def client_for(self, account_id: int, *, unlocked: bool = True):
        db = sqlite3.connect(self.db_path)
        try:
            auth_version = db.execute(
                "SELECT auth_version FROM account_users WHERE id=?",
                (account_id,),
            ).fetchone()[0]
        finally:
            db.close()

        client = self.app.test_client()
        with client.session_transaction() as session:
            session["account_user_id"] = account_id
            session["family_id"] = 1
            session["auth_version"] = int(auth_version or 0)
            session["csrf_token"] = "test-token"
            if unlocked:
                session["parent_authenticated"] = True
        return client

    def test_parent_two_cannot_reset_shared_pin(self):
        client = self.client_for(self.parent_two_id, unlocked=False)
        response = client.post(
            "/parent/reset-pin",
            data={
                "csrf_token": "test-token",
                "account_password": "ParentTwoPassword123",
                "new_pin": "2468",
                "confirm_pin": "2468",
            },
        )
        self.assertEqual(response.status_code, 403)

    def test_parent_two_cannot_change_pin_from_profile(self):
        client = self.client_for(self.parent_two_id)
        page = client.get("/account/profile")
        self.assertEqual(page.status_code, 200)
        self.assertNotIn(b"Change Parent PIN", page.data)
        self.assertIn(b"Only Parent One", page.data)

        response = client.post(
            "/account/profile",
            data={
                "csrf_token": "test-token",
                "form_action": "change_pin",
                "current_pin": "1234",
                "new_pin": "2468",
                "confirm_pin": "2468",
            },
        )
        self.assertEqual(response.status_code, 403)

    def test_owner_removal_disables_membership_and_invalidates_session(self):
        parent_two_client = self.client_for(self.parent_two_id)
        owner_client = self.client_for(1)

        response = owner_client.post(
            f"/parent/management/remove/{self.parent_two_id}",
            data={"csrf_token": "test-token"},
        )
        self.assertEqual(response.status_code, 302)

        db = sqlite3.connect(self.db_path)
        try:
            membership = db.execute(
                """SELECT active FROM family_memberships
                   WHERE family_id=1 AND account_user_id=?""",
                (self.parent_two_id,),
            ).fetchone()
            auth_version = db.execute(
                "SELECT auth_version FROM account_users WHERE id=?",
                (self.parent_two_id,),
            ).fetchone()[0]
        finally:
            db.close()

        self.assertEqual(membership[0], 0)
        self.assertEqual(auth_version, 1)

        stale_session_response = parent_two_client.get("/parent/")
        self.assertEqual(stale_session_response.status_code, 302)
        self.assertIn("/account/login", stale_session_response.location)


if __name__ == "__main__":
    unittest.main(verbosity=2)
