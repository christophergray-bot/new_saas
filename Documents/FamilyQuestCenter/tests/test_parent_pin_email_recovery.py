"""Regression tests for FC-0023 Parent PIN email recovery."""
from pathlib import Path
import os
import tempfile
import unittest
import uuid
from unittest.mock import patch

os.environ.setdefault("SECRET_KEY", "test-secret-key")

from app import create_app
from database import get_db
from services.account_tokens import (
    consume_pin_reset,
    create_pin_reset_token,
    get_valid_pin_reset,
)


class ParentPinEmailRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        db_path = Path(self.tempdir.name) / "test.db"
        self.app = create_app({
            "TESTING": True,
            "DATABASE_PATH": db_path,
            "SECRET_KEY": "test-secret-key",
            "SESSION_COOKIE_SECURE": False,
        })
        self.client = self.app.test_client()

        with self.app.app_context():
            db = get_db()
            unique = uuid.uuid4().hex
            self.family_id = db.execute(
                "INSERT INTO families(name,slug,status) VALUES(?,?,'active')",
                (f"PIN Test Family {unique}", f"pin-test-{unique}"),
            ).lastrowid
            self.account_id = db.execute(
                """INSERT INTO account_users
                   (email,password_hash,display_name,email_verified,active,platform_role)
                   VALUES(?,?,?,1,1,'none')""",
                (f"pin-{unique}@example.com", "unused", "Parent"),
            ).lastrowid
            db.execute(
                """INSERT INTO family_memberships
                   (family_id,account_user_id,role,active)
                   VALUES(?,?, 'owner',1)""",
                (self.family_id, self.account_id),
            )
            db.commit()

    def tearDown(self):
        self.tempdir.cleanup()

    def test_pin_token_is_family_scoped_single_use(self):
        with self.app.app_context():
            token = create_pin_reset_token(self.account_id, self.family_id)
            row = get_valid_pin_reset(token)
            self.assertIsNotNone(row)
            self.assertEqual(row["family_id"], self.family_id)
            self.assertEqual(
                consume_pin_reset(token),
                (self.account_id, self.family_id),
            )
            self.assertIsNone(get_valid_pin_reset(token))
            self.assertIsNone(consume_pin_reset(token))

    def test_new_request_invalidates_previous_token(self):
        with self.app.app_context():
            old_token = create_pin_reset_token(self.account_id, self.family_id)
            new_token = create_pin_reset_token(self.account_id, self.family_id)
            self.assertIsNone(get_valid_pin_reset(old_token))
            self.assertIsNotNone(get_valid_pin_reset(new_token))


if __name__ == "__main__":
    unittest.main()
