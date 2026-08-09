"""Regression coverage for ADJ-0017 and ADJ-0018."""
import os
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ArchiveRewardsPassTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="fqc-archive-rewards-"))
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

            cls.reward_id = connection.execute(
                """INSERT INTO rewards
                   (name,description,icon,cost,quantity,requires_approval,
                    active,family_id)
                   VALUES('Archive Test Reward','Test reward','🎁',10,NULL,1,1,?)""",
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

    def setUp(self):
        connection = sqlite3.connect(self.db_path)
        try:
            connection.execute(
                """UPDATE rewards
                   SET active=1,
                       name='Archive Test Reward',
                       description='Test reward',
                       icon='🎁',
                       cost=10,
                       quantity=NULL,
                       requires_approval=1
                   WHERE id=?""",
                (self.reward_id,),
            )
            connection.commit()
        finally:
            connection.close()

    def _client(self):
        client = self.app.test_client()
        with client.session_transaction() as session:
            session["account_user_id"] = self.account_id
            session["family_id"] = self.family_id
            session["auth_version"] = self.auth_version
            session["parent_authenticated"] = True
        return client

    def _csrf(self, client, path="/parent/rewards/"):
        client.get(path)
        with client.session_transaction() as session:
            return session["csrf_token"]

    def test_reward_card_keeps_edit_and_removes_archive_action(self):
        rendered = self._client().get("/parent/rewards/").get_data(as_text=True)
        self.assertIn(
            f'/parent/rewards/{self.reward_id}/edit',
            rendered,
        )
        self.assertNotIn(
            f'/parent/rewards/{self.reward_id}/toggle',
            rendered,
        )

    def test_reward_edit_contains_archive_action_and_no_active_checkbox(self):
        rendered = self._client().get(
            f"/parent/rewards/{self.reward_id}/edit"
        ).get_data(as_text=True)
        self.assertIn("<h2>Archive Reward</h2>", rendered)
        self.assertIn("📦 Archive Reward", rendered)
        self.assertNotIn('name="active"', rendered)
        self.assertNotIn("Active and visible", rendered)

    def test_editing_reward_preserves_active_status(self):
        client = self._client()
        response = client.post(
            f"/parent/rewards/{self.reward_id}/edit",
            data={
                "csrf_token": self._csrf(
                    client,
                    f"/parent/rewards/{self.reward_id}/edit",
                ),
                "name": "Archive Test Reward Updated",
                "description": "Updated",
                "icon": "🎁",
                "cost": "15",
                "quantity": "",
                "requires_approval": "on",
                # Deliberately no active field.
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)

        connection = sqlite3.connect(self.db_path)
        try:
            active = connection.execute(
                "SELECT active FROM rewards WHERE id=?",
                (self.reward_id,),
            ).fetchone()[0]
        finally:
            connection.close()
        self.assertEqual(active, 1)

    def test_archive_action_archives_reward(self):
        client = self._client()
        response = client.post(
            f"/parent/rewards/{self.reward_id}/toggle",
            data={"csrf_token": self._csrf(client)},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)

        connection = sqlite3.connect(self.db_path)
        try:
            active = connection.execute(
                "SELECT active FROM rewards WHERE id=?",
                (self.reward_id,),
            ).fetchone()[0]
        finally:
            connection.close()
        self.assertEqual(active, 0)


if __name__ == "__main__":
    unittest.main()
