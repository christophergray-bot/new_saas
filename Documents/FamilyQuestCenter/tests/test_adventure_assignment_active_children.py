"""Regression test for FC-0023: archived children are not assignable to Adventures."""
from __future__ import annotations

import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

from tests.fixture_utils import ensure_primary_family_fixture


class AdventureAssignmentActiveChildrenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="fqc-adventure-active-children-"))
        cls.db_path = cls.tmpdir / "adventure-children.db"
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
                "INSERT INTO users(name,role,initial,active,total_points,total_xp,current_level,current_streak,avatar_key,title_key,frame_key,theme_key,family_id) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                ("FC Active Child", "child", "A", 1, 0, 0, 1, 0, "adventurer", "adventurer", "bronze", "quest", 1),
            )
            db.execute(
                "INSERT INTO users(name,role,initial,active,total_points,total_xp,current_level,current_streak,avatar_key,title_key,frame_key,theme_key,family_id) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                ("FC Archived Child", "child", "Z", 0, 0, 0, 1, 0, "adventurer", "adventurer", "bronze", "quest", 1),
            )
            cursor = db.execute(
                "INSERT INTO adventures_v2(name,description,bonus_xp,active,family_id) VALUES(?,?,?,?,?)",
                ("FC Assignment Adventure", "", 100, 1, 1),
            )
            self.adventure_id = cursor.lastrowid
            db.commit()
        finally:
            db.close()

    def _client(self):
        connection = sqlite3.connect(self.db_path)
        try:
            auth_version = int(connection.execute(
                "SELECT auth_version FROM account_users WHERE id=1"
            ).fetchone()[0] or 0)
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

    def test_adventure_assignment_hides_archived_children(self):
        response = self._client().get(f"/parent/adventures/{self.adventure_id}/assign")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"FC Active Child", response.data)
        self.assertNotIn(b"FC Archived Child", response.data)


if __name__ == "__main__":
    unittest.main(verbosity=2)
