"""Regression tests for Stripe subscription access state."""
from __future__ import annotations

import re
import shutil
import tempfile
import unittest
from pathlib import Path

from app import create_app
from database import get_db
from models.settings import set_setting
from werkzeug.security import generate_password_hash
from services.billing import attach_checkout_to_family, family_has_access

ROOT = Path(__file__).resolve().parents[1]


class StripeBillingStateTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="fqc-stripe-"))
        self.db_path = self.tmpdir / "billing.db"
        shutil.copy2(ROOT / "tests" / "fixtures" / "baseline.db", self.db_path)
        self.app = create_app({
            "TESTING": True,
            "DATABASE_PATH": self.db_path,
            "STRIPE_ENFORCE_SUBSCRIPTIONS": False,
            "PAYMENTS_MODE": "test",
        })

    def tearDown(self):
        shutil.rmtree(self.tmpdir)


    def _setup_application_owner(self, app, client):
        """Establish the platform owner for both fresh and seeded test databases.

        The production setup route must only run when *no* accounts exist. Most
        billing tests copy the seeded ``chorce.db`` fixture, which intentionally
        contains account rows, so those tests seed the platform role directly
        instead of weakening the one-time production setup safeguard.
        """
        with app.app_context():
            db = get_db()
            existing_owner = db.execute(
                "SELECT id FROM account_users WHERE platform_role='application_owner' AND active=1 LIMIT 1"
            ).fetchone()
            account_count = db.execute("SELECT COUNT(*) FROM account_users").fetchone()[0]

            if existing_owner is not None:
                set_setting("installation_owner_account_id", str(existing_owner["id"]))
                return

            if account_count:
                owner_id = db.execute(
                    """INSERT INTO account_users(
                           email,password_hash,display_name,email_verified,active,platform_role
                       ) VALUES(?,?,?,1,1,'application_owner')""",
                    (
                        "platform-owner@example.com",
                        generate_password_hash("PlatformOwner123"),
                        "Application Owner",
                    ),
                ).lastrowid
                set_setting("installation_owner_account_id", str(owner_id))
                db.commit()
                return

        response = client.get("/account/setup-owner")
        self.assertEqual(response.status_code, 200)
        match = re.search(rb'name="csrf_token" value="([^"]+)"', response.data)
        self.assertIsNotNone(match)
        response = client.post(
            "/account/setup-owner",
            data={
                "csrf_token": match.group(1).decode(),
                "display_name": "Application Owner",
                "email": "platform-owner@example.com",
                "password": "PlatformOwner123",
                "confirm_password": "PlatformOwner123",
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        with client.session_transaction() as browser_session:
            browser_session.clear()

    def test_billing_plan_is_public_before_account_creation(self):
        client = self.app.test_client()
        response = client.get("/billing/", follow_redirects=False)
        self.assertEqual(response.status_code, 200)

    def test_billing_status_still_requires_account_login(self):
        client = self.app.test_client()
        response = client.get("/billing/status", follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/account/login", response.headers["Location"])

    def test_active_checkout_grants_family_access(self):
        with self.app.app_context():
            attach_checkout_to_family({
                "customer_id": "cus_test",
                "subscription_id": "sub_test",
                "checkout_session_id": "cs_test",
                "email": "owner@example.com",
                "status": "active",
                "current_period_end": None,
                "cancel_at_period_end": 0,
            }, 1, 1)
            self.assertTrue(family_has_access(1))

    def test_registration_redirects_to_billing_when_stripe_test_checkout_is_configured(self):
        app = create_app({
            "TESTING": True,
            "DATABASE_PATH": self.db_path,
            "STRIPE_ENFORCE_SUBSCRIPTIONS": False,
            "PAYMENTS_MODE": "test",
            "STRIPE_SECRET_KEY": "sk_test_example",
            "STRIPE_PRICE_ID": "price_example",
        })
        client = app.test_client()
        self._setup_application_owner(app, client)
        response = client.get("/account/register", follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/billing", response.headers["Location"])

    def test_landing_page_advertises_monthly_membership_and_uses_billing_link(self):
        app = create_app({
            "TESTING": True,
            "DATABASE_PATH": self.db_path,
            "PAYMENTS_MODE": "test",
            "STRIPE_SECRET_KEY": "sk_test_example",
            "STRIPE_PRICE_ID": "price_example",
        })
        client = app.test_client()
        response = client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"$4.99", response.data)
        self.assertIn(b"/billing", response.data)


if __name__ == "__main__":
    unittest.main()
