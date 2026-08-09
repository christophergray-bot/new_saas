"""Security regression tests for local hardening items 16-20.

The suite always copies chorce.db to a temporary directory. It does not modify
or restore the working database.
"""
import csv
import io
import json
import os
import shutil
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

from tests.fixture_utils import ensure_primary_family_fixture

import sys
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class Security1620Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="fqc-security-16-20-"))
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
            "BACKUP_DIRECTORY": cls.tmpdir / "backups",
            "SESSION_COOKIE_SECURE": False,
        })

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def setUp(self):
        # Restore an unchanged logical SQLite snapshot before each test. Using
        # SQLite's backup API avoids Windows file-lock and WAL-state problems
        # that can occur when replacing the database file with shutil.copy2.
        source = sqlite3.connect(ROOT / "tests" / "fixtures" / "baseline.db")
        destination = sqlite3.connect(self.db_path)
        try:
            source.backup(destination)
        finally:
            destination.close()
            source.close()
        ensure_primary_family_fixture(self.db_path)
        backup_dir = self.tmpdir / "backups"
        if backup_dir.exists():
            shutil.rmtree(backup_dir)
        backup_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_security_fixture()

    def _ensure_security_fixture(self):
        """Create isolated cross-family/non-owner test data when the working DB lacks it."""
        connection = sqlite3.connect(self.db_path)
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            owner_setting = connection.execute(
                "SELECT value FROM settings WHERE key='installation_owner_account_id'"
            ).fetchone()
            installation_owner_id = int(owner_setting[0]) if owner_setting else 1

            row = connection.execute(
                "SELECT fm.account_user_id, fm.family_id "
                "FROM family_memberships fm "
                "JOIN account_users au ON au.id=fm.account_user_id "
                "JOIN families f ON f.id=fm.family_id "
                "WHERE fm.active=1 AND au.active=1 AND f.status='active' "
                "AND fm.account_user_id<>? ORDER BY fm.account_user_id LIMIT 1",
                (installation_owner_id,),
            ).fetchone()

            if row is None:
                family_cursor = connection.execute(
                    "INSERT INTO families(name, slug, status) VALUES(?, ?, 'active')",
                    ('Security Fixture Family', 'security-fixture-family'),
                )
                family_id = int(family_cursor.lastrowid)
                account_cursor = connection.execute(
                    "INSERT INTO account_users(email, password_hash, display_name, active) "
                    "VALUES(?, ?, ?, 1)",
                    ('security-fixture@example.invalid', 'test-only-password-hash', 'Security Fixture Parent'),
                )
                account_id = int(account_cursor.lastrowid)
                connection.execute(
                    "INSERT INTO family_memberships(family_id, account_user_id, role, active) "
                    "VALUES(?, ?, 'parent', 1)",
                    (family_id, account_id),
                )
            else:
                account_id, family_id = int(row[0]), int(row[1])

            child = connection.execute(
                "SELECT id FROM users WHERE family_id=? ORDER BY id LIMIT 1", (family_id,)
            ).fetchone()
            if child is None:
                child_id = int(connection.execute(
                    "INSERT INTO users(name, role, initial, active, family_id) "
                    "VALUES('Fixture Child', 'child', 'F', 1, ?)",
                    (family_id,),
                ).lastrowid)
            else:
                child_id = int(child[0])

            quest = connection.execute(
                "SELECT id FROM chores WHERE family_id=? ORDER BY id LIMIT 1", (family_id,)
            ).fetchone()
            if quest is None:
                connection.execute(
                    "INSERT INTO chores(title, description, difficulty, stars, approval_required, active, family_id) "
                    "VALUES('Security Fixture Quest', 'Cross-family test record', 1, 5, 1, 1, ?)",
                    (family_id,),
                )

            reward = connection.execute(
                "SELECT id FROM rewards WHERE family_id=? ORDER BY id LIMIT 1", (family_id,)
            ).fetchone()
            if reward is None:
                reward_id = int(connection.execute(
                    "INSERT INTO rewards(name, description, icon, cost, requires_approval, active, family_id) "
                    "VALUES('Security Fixture Reward', 'Cross-family test record', '🎁', 5, 1, 1, ?)",
                    (family_id,),
                ).lastrowid)
            else:
                reward_id = int(reward[0])

            request_row = connection.execute(
                "SELECT id FROM reward_requests WHERE family_id=? ORDER BY id LIMIT 1", (family_id,)
            ).fetchone()
            if request_row is None:
                connection.execute(
                    "INSERT INTO reward_requests(reward_id, child_id, status, family_id) "
                    "VALUES(?, ?, 'pending', ?)",
                    (reward_id, child_id, family_id),
                )

            connection.commit()
        finally:
            connection.close()

    def client_for(self, account_id=1, family_id=1, unlocked=True):
        connection = sqlite3.connect(self.db_path)
        try:
            row = connection.execute(
                "SELECT auth_version FROM account_users WHERE id=?",
                (account_id,),
            ).fetchone()
            self.assertIsNotNone(row, f"Missing test account {account_id}")
            auth_version = int(row[0] or 0)
        finally:
            connection.close()

        client = self.app.test_client()
        with client.session_transaction() as session:
            session["account_user_id"] = account_id
            session["family_id"] = family_id
            session["auth_version"] = auth_version
            session["csrf_token"] = "test-token"
            if unlocked:
                session["parent_authenticated"] = True
        return client

    def scalar(self, sql, params=()):
        connection = sqlite3.connect(self.db_path)
        try:
            return connection.execute(sql, params).fetchone()[0]
        finally:
            connection.close()

    def foreign_id(self, table, family_id=2):
        connection = sqlite3.connect(self.db_path)
        try:
            row = connection.execute(
                f'SELECT id FROM "{table}" WHERE family_id=? ORDER BY id LIMIT 1',
                (family_id,),
            ).fetchone()
            self.assertIsNotNone(row, f"Test data needs a family {family_id} row in {table}")
            return int(row[0])
        finally:
            connection.close()

    # Item 16: modified URL/object-ID cross-family checks.
    def test_cross_family_child_url_is_not_found(self):
        response = self.client_for().get(f"/parent/children/{self.foreign_id('users')}")
        self.assertEqual(response.status_code, 404)

    def test_cross_family_quest_edit_does_not_expose_record(self):
        response = self.client_for().get(f"/parent/quests/{self.foreign_id('chores')}/edit")
        self.assertIn(response.status_code, (302, 404))
        self.assertNotIn(b"Hardning Test", response.data)

    def test_cross_family_reward_edit_is_not_found(self):
        response = self.client_for().get(f"/parent/rewards/{self.foreign_id('rewards')}/edit")
        self.assertEqual(response.status_code, 404)

    def test_cross_family_reward_toggle_cannot_change_other_family(self):
        reward_id = self.foreign_id("rewards")
        before = self.scalar("SELECT active FROM rewards WHERE id=?", (reward_id,))
        response = self.client_for().post(
            f"/parent/rewards/{reward_id}/toggle", data={"csrf_token": "test-token"}
        )
        self.assertEqual(response.status_code, 404)
        after = self.scalar("SELECT active FROM rewards WHERE id=?", (reward_id,))
        self.assertEqual(before, after)

    def test_cross_family_reward_request_approval_cannot_change_record(self):
        request_id = self.foreign_id("reward_requests")
        before = self.scalar("SELECT status FROM reward_requests WHERE id=?", (request_id,))
        response = self.client_for().post(
            f"/parent/rewards/requests/{request_id}/approve",
            data={"csrf_token": "test-token"},
        )
        self.assertEqual(response.status_code, 302)
        after = self.scalar("SELECT status FROM reward_requests WHERE id=?", (request_id,))
        self.assertEqual(before, after)

    # Item 17: persisted logging redaction.
    def test_audit_log_redacts_common_secrets(self):
        from models.administration import log_audit
        with self.app.test_request_context("/"):
            from flask import session
            session["account_user_id"] = 1
            session["family_id"] = 1
            log_audit(
                "security_test",
                "test",
                details="password=hunter2 pin:1234 csrf_token=abc secret=xyz session_id=qwerty",
            )
        connection = sqlite3.connect(self.db_path)
        try:
            details = connection.execute(
                "SELECT details FROM audit_log WHERE action='security_test' ORDER BY id DESC LIMIT 1"
            ).fetchone()[0]
        finally:
            connection.close()
        self.assertNotIn("hunter2", details)
        self.assertNotIn("1234", details)
        self.assertNotIn("abc", details)
        self.assertIn("[REDACTED]", details)

    # Item 18: backup and restore tests use only the temporary database.
    def test_backup_create_integrity_delete_and_path_traversal(self):
        from models.reliability import create_database_backup, delete_backup, get_backup_path
        with self.app.app_context():
            backup = create_database_backup()
            self.assertTrue(backup.exists())
            connection = sqlite3.connect(backup)
            try:
                self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            finally:
                connection.close()
            with self.assertRaises(ValueError):
                get_backup_path("../chorce.db")
            delete_backup(backup.name)
            self.assertFalse(backup.exists())

    def test_corrupt_backup_is_rejected_without_replacing_database(self):
        from models.reliability import backup_directory, restore_backup
        original_hash = self.db_path.read_bytes()
        with self.app.app_context():
            corrupt = backup_directory() / "corrupt_test.db"
            corrupt.write_bytes(b"not a sqlite database")
            with self.assertRaises((sqlite3.DatabaseError, RuntimeError)):
                restore_backup(corrupt.name)
            self.assertEqual(original_hash, self.db_path.read_bytes())
            corrupt.unlink(missing_ok=True)

    def test_valid_restore_creates_safety_copy(self):
        from models.reliability import create_database_backup, restore_backup
        with self.app.app_context():
            backup = create_database_backup()
            connection = sqlite3.connect(self.db_path)
            connection.execute("UPDATE families SET name='Temporary Changed Name' WHERE id=1")
            connection.commit()
            connection.close()
            safety = restore_backup(backup.name)
            self.assertTrue(safety.exists())
            self.assertNotEqual(
                self.scalar("SELECT name FROM families WHERE id=1"),
                "Temporary Changed Name",
            )

    def test_restore_uses_sqlite_copy_without_restore_temp_file(self):
        from models.reliability import create_database_backup, restore_backup
        with self.app.app_context():
            backup = create_database_backup()
            restore_backup(backup.name)
            self.assertFalse(self.db_path.with_suffix(".restore.tmp").exists())
            connection = sqlite3.connect(self.db_path)
            try:
                self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            finally:
                connection.close()

    # Item 19: restrictive foreign-key behavior is deliberate and verified.
    def test_foreign_keys_are_enabled_and_block_orphaning_child_delete(self):
        connection = sqlite3.connect(self.db_path)
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            self.assertEqual(connection.execute("PRAGMA foreign_keys").fetchone()[0], 1)
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("DELETE FROM users WHERE id=1")
                connection.commit()
            connection.rollback()
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM users WHERE id=1").fetchone()[0], 1)
        finally:
            connection.close()

    def test_foreign_key_check_has_no_violations(self):
        connection = sqlite3.connect(self.db_path)
        try:
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
        finally:
            connection.close()

    # Item 20: exported tenant data must never include another family.
    def test_family_export_contains_only_active_family_rows(self):
        from models.reliability import build_export_zip
        with self.app.test_request_context("/"):
            from flask import session
            session["account_user_id"] = 1
            session["family_id"] = 1
            archive_bytes = build_export_zip().getvalue()
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            self.assertEqual(manifest["family_id"], 1)
            self.assertEqual(manifest["scope"], "active_family_only")
            for filename in archive.namelist():
                if not filename.endswith(".csv"):
                    continue
                rows = list(csv.DictReader(io.StringIO(archive.read(filename).decode("utf-8"))))
                for row in rows:
                    if "family_id" in row and row["family_id"]:
                        self.assertEqual(int(row["family_id"]), 1, filename)



    def test_platform_owner_without_family_membership_can_access_owner_dashboard(self):
        connection = sqlite3.connect(self.db_path)
        try:
            owner_setting = connection.execute(
                "SELECT value FROM settings WHERE key='installation_owner_account_id'"
            ).fetchone()
            owner_id = int(owner_setting[0]) if owner_setting else 1
            connection.execute(
                "UPDATE account_users SET platform_role='application_owner', active=1 WHERE id=?",
                (owner_id,),
            )
            connection.execute(
                "DELETE FROM family_memberships WHERE account_user_id=?",
                (owner_id,),
            )
            auth_version = connection.execute(
                "SELECT COALESCE(auth_version,0) FROM account_users WHERE id=?",
                (owner_id,),
            ).fetchone()[0]
            connection.commit()
        finally:
            connection.close()

        client = self.app.test_client()
        with client.session_transaction() as owner_session:
            owner_session["account_user_id"] = owner_id
            owner_session["auth_version"] = int(auth_version or 0)
            owner_session["csrf_token"] = "test-token"

        response = client.get("/developer/")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b"Sign in to Family Quest Center", response.data)

    def test_second_owner_cannot_access_system_backup_center(self):
        connection = sqlite3.connect(self.db_path)
        try:
            row = connection.execute(
                "SELECT account_user_id, family_id FROM family_memberships "
                "WHERE role='owner' AND account_user_id<>1 ORDER BY account_user_id LIMIT 1"
            ).fetchone()
            if row is None:
                self.skipTest("Test database does not contain a second owner account")
            account_id, family_id = int(row[0]), int(row[1])
        finally:
            connection.close()
        response = self.client_for(account_id=account_id, family_id=family_id).get("/maintenance/")
        self.assertEqual(response.status_code, 403)

    def _non_installation_owner_membership(self):
        connection = sqlite3.connect(self.db_path)
        try:
            owner_setting = connection.execute(
                "SELECT value FROM settings WHERE key='installation_owner_account_id'"
            ).fetchone()
            installation_owner_id = int(owner_setting[0]) if owner_setting else 1
            row = connection.execute(
                "SELECT account_user_id, family_id FROM family_memberships "
                "WHERE active=1 AND account_user_id<>? ORDER BY account_user_id LIMIT 1",
                (installation_owner_id,),
            ).fetchone()
            self.assertIsNotNone(row, "Test database needs a non-installation-owner membership")
            return int(row[0]), int(row[1])
        finally:
            connection.close()

    def test_parent_can_access_family_export_but_not_database_backups(self):
        account_id, family_id = self._non_installation_owner_membership()
        connection = sqlite3.connect(self.db_path)
        try:
            connection.execute(
                "UPDATE family_memberships SET role='parent' WHERE account_user_id=? AND family_id=?",
                (account_id, family_id),
            )
            connection.commit()
        finally:
            connection.close()
        client = self.client_for(account_id=account_id, family_id=family_id)
        self.assertEqual(client.get("/maintenance/").status_code, 403)
        self.assertEqual(client.get("/maintenance/family-export").status_code, 200)
        self.assertEqual(client.get("/maintenance/export").status_code, 200)

    def test_parent_role_cannot_access_system_backup_center(self):
        account_id, family_id = self._non_installation_owner_membership()
        connection = sqlite3.connect(self.db_path)
        try:
            connection.execute(
                "UPDATE family_memberships SET role='parent' WHERE account_user_id=? AND family_id=?",
                (account_id, family_id),
            )
            connection.commit()
        finally:
            connection.close()
        response = self.client_for(account_id=account_id, family_id=family_id).get("/maintenance/")
        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main(verbosity=2)
