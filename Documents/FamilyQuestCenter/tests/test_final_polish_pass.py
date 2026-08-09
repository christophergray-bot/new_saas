"""Regression coverage for final UI, family-page, and footer polish."""
import os
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


class FinalPolishPassTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir=Path(tempfile.mkdtemp(prefix="fqc-final-polish-"))
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
            owner=connection.execute(
                """SELECT id,COALESCE(auth_version,0)
                   FROM account_users
                   WHERE platform_role='application_owner' AND active=1
                   LIMIT 1"""
            ).fetchone()
            if owner is None:
                owner_id=connection.execute(
                    """INSERT INTO account_users
                       (email,password_hash,display_name,email_verified,active,
                        platform_role,auth_version)
                       VALUES(
                           'final-polish-owner@example.com',
                           'test-owner-password-hash',
                           'Final Polish Owner',
                           1,1,'application_owner',0
                       )"""
                ).lastrowid
                owner=(owner_id,0)

            cls.owner_id=int(owner[0])
            cls.owner_auth_version=int(owner[1] or 0)

            # Keep the selected family Parent distinct from the installation
            # owner so role-specific footer assertions exercise Parent mode.
            connection.execute(
                """INSERT INTO settings(key,value)
                   VALUES('installation_owner_account_id',?)
                   ON CONFLICT(key) DO UPDATE SET value=excluded.value""",
                (str(cls.owner_id),),
            )
            connection.commit()
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

    def test_public_footer_has_privacy_terms_contact_and_version(self):
        rendered=self.app.test_client().get("/").get_data(as_text=True)
        for label in ["Privacy","Terms","Contact","Version"]:
            self.assertIn(label,rendered)

    def test_parent_footer_has_no_contact_link(self):
        rendered=self._parent_client().get("/parent/").get_data(as_text=True)
        self.assertIn(">Privacy<",rendered)
        self.assertIn(">Terms<",rendered)
        self.assertNotIn(">Contact<",rendered)
        self.assertIn("Version",rendered)

    def test_family_dashboard_has_greeting_and_family_adventures(self):
        rendered=self._parent_client().get("/family").get_data(as_text=True)
        self.assertIn("Pick your explorer and get started!",rendered)
        self.assertIn("<h2 id=\"family-adventures-heading\">Family Adventures</h2>",rendered)
        for label in ["Pack Store","Quest Books"]:
            self.assertIn(label,rendered)
        self.assertIn("Curated content",rendered)
        self.assertIn("Choose your path",rendered)
        self.assertNotIn("Story Engine",rendered)
        self.assertNotIn("Seasonal Events",rendered)
        self.assertNotIn("Family Challenges",rendered)
        self.assertIn("family-adventures-compact",rendered)
        self.assertNotIn("family-dashboard-parent-access",rendered)
        self.assertLess(
            rendered.index("profile-selector-grid"),
            rendered.index("family-adventures-compact"),
        )

    def test_parent_dashboard_uses_assigned_terminology(self):
        rendered=self._parent_client().get("/parent/").get_data(as_text=True)
        self.assertIn("Assigned Quests",rendered)
        self.assertIn("Assigned Adventures",rendered)
        self.assertNotIn("Today's Missions",rendered)
        self.assertNotIn("Active Adventures",rendered)

    def test_public_information_pages_are_reachable(self):
        client=self.app.test_client()
        for path,title in [
            ("/privacy","Privacy"),
            ("/terms","Terms"),
            ("/contact","Contact"),
        ]:
            response=client.get(path)
            self.assertEqual(response.status_code,200)
            self.assertIn(title,response.get_data(as_text=True))


if __name__=="__main__":
    unittest.main()


def test_family_pack_store_has_back_to_family_profile_button():
    root = Path(__file__).resolve().parents[1]
    template = (root / "templates/parent/content_packs/store.html").read_text(encoding="utf-8")
    assert "{% if request_mode %}" in template
    assert "← Back to Family Profile" in template
    assert "url_for('home.family_dashboard')" in template
