"""Regression coverage for child Complete Quest/Chapter CSRF handling."""
import os
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ChildCompletionCsrfTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="fqc-child-completion-csrf-"))
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

        connection = sqlite3.connect(cls.db_path)
        try:
            row = connection.execute(
                """SELECT a.id, a.child_id, a.family_id, au.id,
                          COALESCE(au.auth_version,0)
                   FROM assignments a
                   JOIN family_memberships fm
                     ON fm.family_id=a.family_id
                    AND fm.active=1
                    AND fm.role IN ('owner','parent')
                   JOIN account_users au
                     ON au.id=fm.account_user_id
                    AND au.active=1
                   WHERE a.status='assigned'
                   ORDER BY a.id LIMIT 1"""
            ).fetchone()
            if row is None:
                raise unittest.SkipTest("No assigned quest exists in seed database")
            cls.assignment_id = int(row[0])
            cls.child_id = int(row[1])
            cls.family_id = int(row[2])
            cls.account_id = int(row[3])
            cls.auth_version = int(row[4] or 0)
        finally:
            connection.close()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def _child_client(self):
        client = self.app.test_client()
        with client.session_transaction() as session:
            session["account_user_id"] = self.account_id
            session["family_id"] = self.family_id
            session["account_role"] = "owner"
            session["auth_version"] = self.auth_version
            session["active_child_id"] = self.child_id
        return client

    def test_child_dashboard_uses_post_form_with_csrf_for_completion(self):
        client = self._child_client()
        response = client.get(f"/child/{self.child_id}")
        self.assertEqual(response.status_code, 200)
        rendered = response.get_data(as_text=True)
        self.assertRegex(
            rendered,
            r'<form method="post" action="/child/complete/\d+">',
        )
        self.assertIn('name="csrf_token"', rendered)

    def test_complete_quest_post_with_valid_csrf_reaches_completion_route(self):
        client = self._child_client()
        page = client.get(f"/child/{self.child_id}?trained=1")
        self.assertEqual(page.status_code, 200)

        with client.session_transaction() as session:
            token = session.get("csrf_token")
        self.assertTrue(token)

        response = client.post(
            f"/child/complete/{self.assignment_id}",
            data={"csrf_token": token},
            follow_redirects=False,
        )
        self.assertNotEqual(response.status_code, 400)

    def test_complete_quest_get_is_not_allowed(self):
        client = self._child_client()
        response = client.get(
            f"/child/complete/{self.assignment_id}",
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 405)


if __name__ == "__main__":
    unittest.main()
