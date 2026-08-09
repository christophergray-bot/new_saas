"""Regression coverage for FC-0019 family settings tenant isolation."""
from __future__ import annotations

import os
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

from tests.fixture_utils import ensure_primary_family_fixture, ensure_secondary_family_fixture


class FamilySettingsIsolationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="fqc-family-settings-"))
        cls.db_path = cls.tmpdir / "settings.db"
        shutil.copy2(ROOT / "tests" / "fixtures" / "baseline.db", cls.db_path)
        os.chdir(ROOT)
        from app import create_app
        cls.app = create_app({
            "TESTING": True,
            "ENVIRONMENT": "development",
            "IS_PRODUCTION": False,
            "SECRET_KEY": "test-secret-key-that-is-long-enough-12345",
            "DATABASE_PATH": cls.db_path,
            "BACKUP_DIRECTORY": cls.tmpdir / "backups",
            "SESSION_COOKIE_SECURE": False,
        })

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def setUp(self):
        source = sqlite3.connect(ROOT / "tests" / "fixtures" / "baseline.db")
        destination = sqlite3.connect(self.db_path)
        try:
            source.backup(destination)
        finally:
            destination.close()
            source.close()
        ensure_primary_family_fixture(self.db_path)

    def client_for(self, account_id: int, family_id: int):
        db = sqlite3.connect(self.db_path)
        try:
            auth_version = db.execute(
                "SELECT auth_version FROM account_users WHERE id=?", (account_id,)
            ).fetchone()[0]
        finally:
            db.close()
        client = self.app.test_client()
        with client.session_transaction() as browser_session:
            browser_session["account_user_id"] = account_id
            browser_session["family_id"] = family_id
            browser_session["auth_version"] = int(auth_version or 0)
            browser_session["parent_authenticated"] = True
            browser_session["csrf_token"] = "test-token"
        return client

    def test_parent_managed_settings_are_isolated_by_family(self):
        secondary_account_id, secondary_family_id = ensure_secondary_family_fixture(self.db_path)
        family_a = self.client_for(1, 1)
        family_b = self.client_for(secondary_account_id, secondary_family_id)

        response = family_a.post("/parent/management/family-settings", data={
            "csrf_token": "test-token",
            "form_action": "quest_defaults",
            "default_quest_difficulty": "5",
            "default_quest_stars": "99",
            "default_approval_required": "on",
        })
        self.assertEqual(response.status_code, 302)

        response = family_b.post("/parent/management/family-settings", data={
            "csrf_token": "test-token",
            "form_action": "quest_defaults",
            "default_quest_difficulty": "2",
            "default_quest_stars": "7",
        })
        self.assertEqual(response.status_code, 302)

        db = sqlite3.connect(self.db_path)
        try:
            rows = db.execute(
                """SELECT family_id,key,value FROM family_settings
                   WHERE family_id IN (?,?)
                     AND key IN ('default_quest_difficulty','default_quest_stars','default_approval_required')""",
                (1, secondary_family_id),
            ).fetchall()
        finally:
            db.close()
        values = {(family_id, key): value for family_id, key, value in rows}
        self.assertEqual(values[(1, "default_quest_difficulty")], "5")
        self.assertEqual(values[(1, "default_quest_stars")], "99")
        self.assertEqual(values[(1, "default_approval_required")], "1")
        self.assertEqual(values[(secondary_family_id, "default_quest_difficulty")], "2")
        self.assertEqual(values[(secondary_family_id, "default_quest_stars")], "7")
        self.assertEqual(values[(secondary_family_id, "default_approval_required")], "0")

    def test_registration_mode_remains_installation_wide(self):
        with self.app.app_context():
            from models.settings import get_registration_mode, set_global_setting
            set_global_setting("registration_mode", "closed")
            self.assertEqual(get_registration_mode("local"), "closed")


if __name__ == "__main__":
    unittest.main(verbosity=2)
