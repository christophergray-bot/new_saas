"""Regression coverage for FC-0021 and ADJ-0015."""
from pathlib import Path
import os
import tempfile
import unittest
import uuid

os.environ.setdefault("SECRET_KEY", "test-secret-key")

from app import create_app
from database import get_db
from werkzeug.security import generate_password_hash
from services.family_security import ensure_family_security_table


class ChildParentAtomicTransitionTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        db_path = Path(self.tempdir.name) / "test.db"
        self.app = create_app({
            "TESTING": True,
            "DATABASE_PATH": db_path,
            "SECRET_KEY": "test-secret-key",
            "SESSION_COOKIE_SECURE": False,
        })
        self.client = self.app.test_client()

        with self.app.app_context():
            db = get_db()
            unique = uuid.uuid4().hex
            family_id = db.execute(
                "INSERT INTO families(name,slug,status) VALUES(?,?,'active')",
                (f"Atomic Test Family {unique}", f"atomic-test-{unique}"),
            ).lastrowid
            account_id = db.execute(
                """INSERT INTO account_users
                   (email,password_hash,display_name,email_verified,active,platform_role)
                   VALUES(?,?,?,1,1,'none')""",
                (f"atomic-{unique}@example.com", generate_password_hash("Password123"), "Parent"),
            ).lastrowid
            db.execute(
                "INSERT INTO family_memberships(family_id,account_user_id,role,active) VALUES(?,?, 'owner',1)",
                (family_id, account_id),
            )
            ensure_family_security_table()
            db.execute(
                """INSERT INTO family_security(family_id,parent_pin_hash)
                   VALUES(?,?)""",
                (family_id, generate_password_hash("2468")),
            )
            child_id = db.execute(
                """INSERT INTO users(family_id,name,role,initial,active)
                   VALUES(?, 'Explorer', 'child', 'E', 1)""",
                (family_id,),
            ).lastrowid
            db.commit()
            self.family_id = family_id
            self.account_id = account_id
            self.child_id = child_id

    def tearDown(self):
        self.tempdir.cleanup()

    def _signed_in_parent(self):
        with self.client.session_transaction() as sess:
            sess["account_user_id"] = self.account_id
            sess["family_id"] = self.family_id
            sess["account_role"] = "owner"
            sess["auth_version"] = 0
            sess["parent_authenticated"] = True

    def test_entering_child_route_locks_parent_and_sets_child_context(self):
        self._signed_in_parent()
        self.client.get(f"/child/{self.child_id}", follow_redirects=False)
        with self.client.session_transaction() as sess:
            self.assertNotIn("parent_authenticated", sess)
            self.assertEqual(sess.get("active_child_id"), self.child_id)

    def test_parent_route_requires_pin_after_child_mode(self):
        self._signed_in_parent()
        self.client.get(f"/child/{self.child_id}", follow_redirects=False)
        response = self.client.get("/parent", follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/parent/login", response.headers["Location"])


if __name__ == "__main__":
    unittest.main()
