"""Regression coverage for FC-0020 Archive Center tenant isolation."""
from __future__ import annotations

import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ArchiveTenantIsolationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="fqc-archive-isolation-"))
        cls.db_path = cls.tmpdir / "archive.db"
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

        db = sqlite3.connect(self.db_path)
        try:
            db.execute(
                "INSERT INTO chores(title,description,difficulty,stars,approval_required,active,family_id) VALUES(?,?,?,?,?,?,?)",
                ("Family A Secret Archived Quest", "", 1, 5, 0, 0, 1),
            )
            db.execute(
                "INSERT INTO chores(title,description,difficulty,stars,approval_required,active,family_id) VALUES(?,?,?,?,?,?,?)",
                ("Family B Archived Quest", "", 1, 5, 0, 0, 2),
            )
            db.execute(
                "INSERT INTO rewards(name,description,icon,cost,requires_approval,active,family_id) VALUES(?,?,?,?,?,?,?)",
                ("Family A Secret Reward", "", "🎁", 5, 1, 0, 1),
            )
            db.execute(
                "INSERT INTO rewards(name,description,icon,cost,requires_approval,active,family_id) VALUES(?,?,?,?,?,?,?)",
                ("Family B Reward", "", "🎁", 5, 1, 0, 2),
            )
            db.execute(
                "INSERT INTO adventures_v2(name,description,bonus_xp,active,family_id) VALUES(?,?,?,?,?)",
                ("Family A Secret Adventure", "", 100, 0, 1),
            )
            db.execute(
                "INSERT INTO adventures_v2(name,description,bonus_xp,active,family_id) VALUES(?,?,?,?,?)",
                ("Family B Archived Adventure", "", 100, 0, 2),
            )
            db.commit()
        finally:
            db.close()

    def client_for(self, account_id: int, family_id: int):
        db = sqlite3.connect(self.db_path)
        try:
            auth_version = db.execute(
                "SELECT auth_version FROM account_users WHERE id=?", (account_id,)
            ).fetchone()[0]
        finally:
            db.close()
        client = self.app.test_client()
        with client.session_transaction() as session:
            session["account_user_id"] = account_id
            session["family_id"] = family_id
            session["auth_version"] = int(auth_version or 0)
            session["parent_authenticated"] = True
            session["csrf_token"] = "test-token"
        return client

    def test_archive_lists_only_current_family_records(self):
        family_b = self.client_for(2, 2)

        quests = family_b.get("/parent/archive/quests")
        self.assertEqual(quests.status_code, 200)
        self.assertIn(b"Family B Archived Quest", quests.data)
        self.assertNotIn(b"Family A Secret Archived Quest", quests.data)

        rewards = family_b.get("/parent/archive/rewards")
        self.assertEqual(rewards.status_code, 200)
        self.assertIn(b"Family B Reward", rewards.data)
        self.assertNotIn(b"Family A Secret Reward", rewards.data)

        adventures = family_b.get("/parent/archive/adventures")
        self.assertEqual(adventures.status_code, 200)
        self.assertIn(b"Family B Archived Adventure", adventures.data)
        self.assertNotIn(b"Family A Secret Adventure", adventures.data)

        center = family_b.get("/parent/archive/")
        self.assertEqual(center.status_code, 200)
        self.assertNotIn(b"Achievements", center.data)

    def test_cross_family_restore_is_rejected(self):
        db = sqlite3.connect(self.db_path)
        try:
            quest_id = db.execute(
                "SELECT id FROM chores WHERE title='Family A Secret Archived Quest'"
            ).fetchone()[0]
        finally:
            db.close()

        family_b = self.client_for(2, 2)
        response = family_b.post(
            f"/parent/archive/quests/quest/{quest_id}/restore",
            data={"csrf_token": "test-token"},
        )
        self.assertEqual(response.status_code, 302)

        db = sqlite3.connect(self.db_path)
        try:
            active = db.execute("SELECT active FROM chores WHERE id=?", (quest_id,)).fetchone()[0]
        finally:
            db.close()
        self.assertEqual(active, 0)


    def test_current_adventure_restore_is_tenant_scoped(self):
        db = sqlite3.connect(self.db_path)
        try:
            own_id = db.execute(
                "SELECT id FROM adventures_v2 WHERE name='Family B Archived Adventure'"
            ).fetchone()[0]
            other_id = db.execute(
                "SELECT id FROM adventures_v2 WHERE name='Family A Secret Adventure'"
            ).fetchone()[0]
        finally:
            db.close()

        family_b = self.client_for(2, 2)
        response = family_b.post(
            f"/parent/archive/adventures/adventure_v2/{own_id}/restore",
            data={"csrf_token": "test-token"},
        )
        self.assertEqual(response.status_code, 302)

        response = family_b.post(
            f"/parent/archive/adventures/adventure_v2/{other_id}/restore",
            data={"csrf_token": "test-token"},
        )
        self.assertEqual(response.status_code, 302)

        db = sqlite3.connect(self.db_path)
        try:
            own_active = db.execute(
                "SELECT active FROM adventures_v2 WHERE id=?", (own_id,)
            ).fetchone()[0]
            other_active = db.execute(
                "SELECT active FROM adventures_v2 WHERE id=?", (other_id,)
            ).fetchone()[0]
        finally:
            db.close()
        self.assertEqual(own_active, 1)
        self.assertEqual(other_active, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
