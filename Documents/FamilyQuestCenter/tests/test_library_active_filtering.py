"""Regression tests for active Quest and Adventure library filtering."""
from __future__ import annotations

import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

from tests.fixture_utils import ensure_primary_family_fixture


class ActiveLibraryFilteringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="fqc-active-libraries-"))
        cls.db_path = cls.tmpdir / "library.db"
        shutil.copy2(ROOT / "tests" / "fixtures" / "baseline.db", cls.db_path)
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

        db = sqlite3.connect(self.db_path)
        try:
            db.execute(
                "INSERT INTO chores(title,description,difficulty,stars,approval_required,active,family_id) VALUES(?,?,?,?,?,?,?)",
                ("FC Active Library Quest", "", 1, 5, 0, 1, 1),
            )
            db.execute(
                "INSERT INTO chores(title,description,difficulty,stars,approval_required,active,family_id) VALUES(?,?,?,?,?,?,?)",
                ("FC Archived Library Quest", "", 1, 5, 0, 0, 1),
            )
            db.execute(
                "INSERT INTO adventures_v2(name,description,bonus_xp,active,family_id) VALUES(?,?,?,?,?)",
                ("FC Active Library Adventure", "", 100, 1, 1),
            )
            db.execute(
                "INSERT INTO adventures_v2(name,description,bonus_xp,active,family_id) VALUES(?,?,?,?,?)",
                ("FC Archived Library Adventure", "", 100, 0, 1),
            )
            db.commit()
        finally:
            db.close()

    def _client(self):
        connection = sqlite3.connect(self.db_path)
        try:
            row = connection.execute(
                "SELECT auth_version FROM account_users WHERE id=1"
            ).fetchone()
            self.assertIsNotNone(row, "Missing installation-owner test account")
            auth_version = int(row[0] or 0)
        finally:
            connection.close()

        client = self.app.test_client()
        with client.session_transaction() as session:
            session["account_user_id"] = 1
            session["family_id"] = 1
            session["auth_version"] = auth_version
            session["csrf_token"] = "test-token"
            session["parent_authenticated"] = True
        return client

    def test_active_libraries_hide_archived_records(self):
        client = self._client()
        quest_response = client.get("/parent/quests/")
        self.assertEqual(quest_response.status_code, 200)
        self.assertIn(b"FC Active Library Quest", quest_response.data)
        self.assertNotIn(b"FC Archived Library Quest", quest_response.data)

        adventure_response = client.get("/parent/adventures")
        self.assertEqual(adventure_response.status_code, 200)
        self.assertIn(b"FC Active Library Adventure", adventure_response.data)
        self.assertNotIn(b"FC Archived Library Adventure", adventure_response.data)


if __name__ == "__main__":
    unittest.main(verbosity=2)
