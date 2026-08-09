"""Regression coverage for ADJ-0013 Subscription Management."""
import os
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ManagementSubscriptionsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="fqc-mgmt-subscriptions-"))
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
            "PAYMENTS_MODE": "stripe_test",
            "STRIPE_SECRET_KEY": "sk_test_example",
            "STRIPE_PRICE_ID": "price_test_example",
        })

        with cls.app.app_context():
            from services.billing import ensure_billing_schema
            ensure_billing_schema()
            from database import get_db
            db = get_db()

            cls.owner_id = db.execute(
                """INSERT INTO account_users
                   (email,password_hash,display_name,email_verified,active,
                    platform_role,auth_version)
                   VALUES('subscription-owner@example.com','unused',
                          'Subscription Owner',1,1,'application_owner',0)"""
            ).lastrowid
            cls.active_family = db.execute(
                "INSERT INTO families(name,slug,status) VALUES('Active Billing Family','active-billing-family','active')"
            ).lastrowid
            cls.past_due_family = db.execute(
                "INSERT INTO families(name,slug,status) VALUES('Past Due Family','past-due-family','active')"
            ).lastrowid
            cls.no_subscription_family = db.execute(
                "INSERT INTO families(name,slug,status) VALUES('No Billing Family','no-billing-family','active')"
            ).lastrowid

            db.execute(
                """INSERT INTO family_subscriptions
                   (family_id,customer_email,status,current_period_end)
                   VALUES(?,?, 'active','2026-09-01T00:00:00')""",
                (cls.active_family, "active@example.com"),
            )
            db.execute(
                """INSERT INTO family_subscriptions
                   (family_id,customer_email,status,grace_until)
                   VALUES(?,?, 'past_due','2026-08-14T00:00:00')""",
                (cls.past_due_family, "pastdue@example.com"),
            )
            db.commit()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def _owner_client(self):
        client = self.app.test_client()
        with client.session_transaction() as session:
            session["account_user_id"] = int(self.owner_id)
            session["auth_version"] = 0
        return client

    def test_subscription_page_displays_metrics_and_family_rows(self):
        response = self._owner_client().get("/developer/subscriptions")
        self.assertEqual(response.status_code, 200)
        rendered = response.get_data(as_text=True)
        self.assertIn("Subscription Management", rendered)
        self.assertIn("Active Billing Family", rendered)
        self.assertIn("Past Due Family", rendered)
        self.assertIn("No Billing Family", rendered)
        self.assertIn("Needs Attention", rendered)
        self.assertIn("Stripe Configuration", rendered)

    def test_subscription_filters_are_applied(self):
        response = self._owner_client().get(
            "/developer/subscriptions?status=past_due&q=Past+Due"
        )
        self.assertEqual(response.status_code, 200)
        rendered = response.get_data(as_text=True)
        self.assertIn("Past Due Family", rendered)
        self.assertNotIn("Active Billing Family", rendered)
        self.assertNotIn("No Billing Family", rendered)

    def test_subscription_rows_link_to_manage_family(self):
        response = self._owner_client().get("/developer/subscriptions")
        self.assertIn(
            f'/developer/families/{self.active_family}'.encode(),
            response.data,
        )


if __name__ == "__main__":
    unittest.main()
