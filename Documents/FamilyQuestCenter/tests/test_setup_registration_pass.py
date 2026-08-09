"""Regression coverage for Setup & Registration pass."""
import os
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class SetupRegistrationPassTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="fqc-setup-registration-"))
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

            # Public family registration is available only after the one-time
            # platform Application Owner bootstrap has been completed.
            owner = connection.execute(
                """SELECT id
                   FROM account_users
                   WHERE platform_role='application_owner' AND active=1
                   LIMIT 1"""
            ).fetchone()
            if owner is None:
                connection.execute(
                    """INSERT INTO account_users
                       (email,password_hash,display_name,email_verified,active,
                        platform_role,auth_version)
                       VALUES(
                           'setup-registration-owner@example.com',
                           'test-owner-password-hash',
                           'Setup Registration Owner',
                           1,1,'application_owner',0
                       )"""
                )
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
            "PAYMENTS_MODE": "test",
            "STRIPE_SECRET_KEY": "sk_test_example",
            "STRIPE_PRICE_ID": "price_test_example",
            "STRIPE_ENFORCE_SUBSCRIPTIONS": True,
            "REGISTRATION_MODE": "open",
        })

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def _parent_client(self):
        connection = sqlite3.connect(self.db_path)
        try:
            connection.execute(
                """INSERT OR IGNORE INTO family_onboarding(family_id,setup_completed)
                   VALUES(?,0)""",
                (self.family_id,),
            )
            connection.execute(
                "UPDATE family_onboarding SET setup_completed=0 WHERE family_id=?",
                (self.family_id,),
            )
            connection.commit()
        finally:
            connection.close()

        client = self.app.test_client()
        with client.session_transaction() as session:
            session["account_user_id"] = self.account_id
            session["family_id"] = self.family_id
            session["auth_version"] = self.auth_version
            session["parent_authenticated"] = True
        return client

    def test_root_register_begins_billing_flow_not_login(self):
        client = self.app.test_client()
        response = client.get("/register", follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/account/register", response.headers["Location"])

        response = client.get(response.headers["Location"], follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/billing", response.headers["Location"])
        self.assertNotIn("/account/login", response.headers["Location"])

    def test_guided_setup_contains_approved_quest_and_adventure_copy(self):
        previous = self.app.config["STRIPE_ENFORCE_SUBSCRIPTIONS"]
        self.app.config["STRIPE_ENFORCE_SUBSCRIPTIONS"] = False
        try:
            rendered = self._parent_client().get(
                "/getting-started/"
            ).get_data(as_text=True)
        finally:
            self.app.config["STRIPE_ENFORCE_SUBSCRIPTIONS"] = previous
        self.assertIn(
            "Open the Quest Library to create and assign quests to your explorers.",
            rendered,
        )
        self.assertIn("Create and assign your first Adventure", rendered)
        self.assertIn(
            "Adventures are made up of Chapters that your explorer completes in order.",
            rendered,
        )

    def test_parent_navigation_uses_back_to_family_setup(self):
        previous = self.app.config["STRIPE_ENFORCE_SUBSCRIPTIONS"]
        self.app.config["STRIPE_ENFORCE_SUBSCRIPTIONS"] = False
        try:
            rendered = self._parent_client().get(
                "/getting-started/"
            ).get_data(as_text=True)
        finally:
            self.app.config["STRIPE_ENFORCE_SUBSCRIPTIONS"] = previous
        self.assertIn("Back to Family Setup", rendered)
        self.assertIn('href="/getting-started/"', rendered)

    def test_registration_copy_does_not_claim_default_reward(self):
        client = self.app.test_client()
        with client.session_transaction() as session:
            session["billing_entitlement"] = {
                "email": "billing@example.com",
                "subscription_id": "sub_test",
                "customer_id": "cus_test",
            }
        response = client.get("/account/register")
        self.assertEqual(response.status_code, 200)
        rendered = response.get_data(as_text=True)
        self.assertIn("one example quest and the Outdoor Adventure", rendered)
        self.assertNotIn("one reward", rendered)


if __name__ == "__main__":
    unittest.main()
