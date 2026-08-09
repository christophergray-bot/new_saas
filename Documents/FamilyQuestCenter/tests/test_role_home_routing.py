"""Regression coverage for FC-0033 role-aware Home and logo routing."""
import os
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class RoleHomeRoutingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="fqc-role-home-"))
        cls.db_path = cls.tmpdir / "test.db"
        shutil.copy2(ROOT / "tests" / "fixtures" / "baseline.db", cls.db_path)
        os.chdir(ROOT)

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

    def client_for(self, account_id=None, family_id=None, *, child_id=None):
        client = self.app.test_client()
        if account_id is not None:
            connection = sqlite3.connect(self.db_path)
            try:
                row = connection.execute(
                    "SELECT auth_version FROM account_users WHERE id=?",
                    (account_id,),
                ).fetchone()
                self.assertIsNotNone(row)
                auth_version = int(row[0] or 0)
            finally:
                connection.close()

            with client.session_transaction() as session:
                session["account_user_id"] = account_id
                session["auth_version"] = auth_version
                if family_id is not None:
                    session["family_id"] = family_id
                    session["account_role"] = "owner"
                if child_id is not None:
                    session["active_child_id"] = child_id
        return client

    def test_public_home_and_logo_route_to_landing(self):
        response = self.app.test_client().get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'class="app-brand" href="/"', response.data)
        self.assertIn(b'<span>Home</span>', response.data)

    def test_parent_and_child_use_role_specific_home_destinations(self):
        connection = sqlite3.connect(self.db_path)
        try:
            family_id = connection.execute(
                "SELECT id FROM families WHERE status='active' ORDER BY id LIMIT 1"
            ).fetchone()[0]
            account_id = connection.execute(
                """INSERT INTO account_users
                   (email,password_hash,display_name,email_verified,
                    active,platform_role,auth_version)
                   VALUES('role-parent@example.com','unused',
                          'Role Parent',1,1,'none',0)"""
            ).lastrowid
            connection.execute(
                """INSERT INTO family_memberships
                   (family_id,account_user_id,role,active)
                   VALUES(?,?, 'parent',1)""",
                (family_id, account_id),
            )
            child_row = connection.execute(
                """SELECT id FROM users
                   WHERE family_id=? AND role='child' AND active=1
                   ORDER BY id LIMIT 1""",
                (family_id,),
            ).fetchone()
            if child_row is None:
                child_id = int(connection.execute(
                    """INSERT INTO users
                       (name,role,initial,active,total_points,total_xp,current_level,current_streak,
                        avatar_key,title_key,frame_key,theme_key,family_id)
                       VALUES('Role Routing Child','child','R',1,0,0,1,0,
                              'adventurer','adventurer','bronze','quest',?)""",
                    (family_id,),
                ).lastrowid)
            else:
                child_id = int(child_row[0])
            connection.commit()
        finally:
            connection.close()

        parent = self.client_for(account_id, family_id).get("/family")
        self.assertEqual(parent.status_code, 200)
        self.assertIn(b'class="app-brand" href="/parent/"', parent.data)
        self.assertIn(b'<span>Family Dashboard</span>', parent.data)

        # This regression test covers role-aware Home/logo destinations, not
        # Explorer Training. The child dashboard intentionally redirects
        # untrained children, so use the route's supported bypass to render
        # the dashboard directly for this focused assertion.
        child = self.client_for(account_id, family_id, child_id=child_id).get(
            f"/child/{child_id}?trained=1"
        )
        self.assertEqual(child.status_code, 200)
        expected = f'class="app-brand" href="/child/{child_id}"'.encode()
        self.assertIn(expected, child.data)
        self.assertIn(b'<span>My Day</span>', child.data)


if __name__ == "__main__":
    unittest.main()
