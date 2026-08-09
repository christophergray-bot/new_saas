"""Regression coverage for final review findings 1-3."""
import os
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


class ReviewFindingsDashboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir=Path(tempfile.mkdtemp(prefix="fqc-review-findings-"))
        cls.db_path=cls.tmpdir/"test.db"
        shutil.copy2(ROOT/"tests"/"fixtures"/"baseline.db",cls.db_path)
        os.chdir(ROOT)
        connection=sqlite3.connect(cls.db_path)
        try:
            row=connection.execute(
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
            "TESTING":True,"ENVIRONMENT":"development","IS_PRODUCTION":False,
            "SECRET_KEY":"test-secret-key-that-is-long-enough-12345",
            "DATABASE_PATH":cls.db_path,"SESSION_COOKIE_SECURE":False,
            "STRIPE_ENFORCE_SUBSCRIPTIONS":False,
        })

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmpdir,ignore_errors=True)

    def _parent_client(self):
        client=self.app.test_client()
        with client.session_transaction() as session:
            session["account_user_id"]=self.account_id
            session["family_id"]=self.family_id
            session["auth_version"]=self.auth_version
            session["parent_authenticated"]=True
        return client

    def test_combined_approval_action_and_reward_management(self):
        rendered=self._parent_client().get("/parent/").get_data(as_text=True)
        self.assertEqual(
            rendered.count("Review Completed Quests and Adventures"),
            1,
        )
        self.assertIn("Reward Management",rendered)
        self.assertIn(
            'href="/parent/rewards/"',
            rendered,
        )

    def test_family_page_review_layout(self):
        rendered=self._parent_client().get("/family").get_data(as_text=True)
        self.assertNotIn("Family Challenges",rendered)
        self.assertIn("family-adventures-actions",rendered)
        self.assertNotIn("family-dashboard-parent-access",rendered)
        self.assertLess(
            rendered.index("profile-selector-grid"),
            rendered.index("family-adventures-compact"),
        )


if __name__=="__main__":
    unittest.main()
