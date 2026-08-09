"""Regression coverage for FC-0030, FC-0031, and ADJ-0016."""
import os
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ChildManagementPassTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="fqc-child-management-"))
        cls.db_path = cls.tmpdir / "test.db"
        shutil.copy2(ROOT / "tests" / "fixtures" / "baseline.db", cls.db_path)
        os.chdir(ROOT)

        connection = sqlite3.connect(cls.db_path)
        try:
            row = connection.execute(
                """SELECT au.id,fm.family_id,COALESCE(au.auth_version,0)
                   FROM account_users au
                   JOIN family_memberships fm ON fm.account_user_id=au.id
                   JOIN families f ON f.id=fm.family_id
                   WHERE au.active=1 AND fm.active=1 AND f.status='active'
                     AND fm.role IN ('owner','parent')
                     AND COALESCE(au.platform_role,'none')<>'application_owner'
                   ORDER BY au.id LIMIT 1"""
            ).fetchone()
            if row is None:
                raise unittest.SkipTest("No ordinary Parent account in baseline")
            cls.account_id = int(row[0])
            cls.family_id = int(row[1])
            cls.auth_version = int(row[2] or 0)

            cls.child_id = connection.execute(
                """INSERT INTO users
                   (name,role,initial,active,total_points,total_xp,current_level,
                    current_streak,avatar_key,title_key,frame_key,theme_key,family_id)
                   VALUES('Detail Explorer','child','D',1,12,34,2,3,
                          'adventurer','adventurer','bronze','quest',?)""",
                (cls.family_id,),
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

    def _client(self):
        client = self.app.test_client()
        with client.session_transaction() as session:
            session["account_user_id"] = self.account_id
            session["family_id"] = self.family_id
            session["auth_version"] = self.auth_version
            session["parent_authenticated"] = True
        return client

    def _csrf(self, client):
        client.get("/parent/children/")
        with client.session_transaction() as session:
            return session["csrf_token"]

    def test_child_details_page_contains_all_required_sections(self):
        response = self._client().get(f"/parent/children/{self.child_id}")
        self.assertEqual(response.status_code, 200)
        rendered = response.get_data(as_text=True)
        for heading in ["Statistics", "Assignments", "Adventures", "Rewards", "Achievements"]:
            self.assertIn(f"<h2>{heading}</h2>", rendered)
        self.assertNotIn("Coming Soon", rendered)

    def test_family_member_card_has_view_and_edit_but_no_archive_action(self):
        rendered = self._client().get("/parent/children/").get_data(as_text=True)
        self.assertIn("👁 View", rendered)
        self.assertIn("✏ Edit", rendered)
        self.assertNotIn(f"/parent/children/{self.child_id}/toggle", rendered)

    def test_archiving_child_returns_to_family_members(self):
        client = self._client()
        response = client.post(
            f"/parent/children/{self.child_id}/toggle",
            data={"csrf_token": self._csrf(client)},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/parent/children/"))

    def test_edit_page_uses_archive_restore_language(self):
        rendered = self._client().get(
            f"/parent/children/{self.child_id}/edit"
        ).get_data(as_text=True)
        self.assertIn("Restore Child", rendered)
        self.assertNotIn("Deactivate Child", rendered)
        self.assertNotIn("Activate Child", rendered)


if __name__ == "__main__":
    unittest.main()
