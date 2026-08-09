"""Regression coverage for ADJ-0020 Parent Dashboard Quick Actions."""
import os
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ParentDashboardQuickActionsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="fqc-parent-dashboard-actions-"))
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
            cls.account_id=int(row[0]); cls.family_id=int(row[1]); cls.auth_version=int(row[2] or 0)
        finally:
            connection.close()

        from app import create_app
        cls.app=create_app({
            "TESTING":True,
            "ENVIRONMENT":"development",
            "IS_PRODUCTION":False,
            "SECRET_KEY":"test-secret-key-that-is-long-enough-12345",
            "DATABASE_PATH":cls.db_path,
            "SESSION_COOKIE_SECURE":False,
        })

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmpdir,ignore_errors=True)

    def test_quick_actions_replace_pending_approvals_card(self):
        client=self.app.test_client()
        with client.session_transaction() as session:
            session["account_user_id"]=self.account_id
            session["family_id"]=self.family_id
            session["auth_version"]=self.auth_version
            session["parent_authenticated"]=True

        response=client.get("/parent/")
        self.assertEqual(response.status_code,200)
        rendered=response.get_data(as_text=True)
        for label in [
            "Assign Quest",
            "Assign Adventure",
            "Review Completed Quests and Adventures",
            "Review Reward Requests",
            "Reward Management",
        ]:
            self.assertIn(label,rendered)
        self.assertIn(
            "Open the Approval Center to celebrate your explorer.",
            rendered,
        )
        self.assertIn(
            "Reward your explorer for their hard work.",
            rendered,
        )
        self.assertIn(
            "Create rewards, categories, prices, and inventory.",
            rendered,
        )
        self.assertEqual(
            rendered.count("Review Completed Quests and Adventures"),
            1,
        )
        self.assertNotIn("Review Completed Adventures", rendered)
        self.assertNotIn(
            'dashboard-main-grid dashboard-action-required-grid',
            rendered,
        )
        self.assertIn("<h2>Pending Approvals</h2>", rendered)
        self.assertIn("<h2>Quick Actions</h2>",rendered)


if __name__=="__main__":
    unittest.main()
