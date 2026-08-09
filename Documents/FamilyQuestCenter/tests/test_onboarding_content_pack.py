"""Regression tests for starter Content Pack installation during registration."""
from __future__ import annotations

import json
import re
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class OnboardingContentPackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(
            tempfile.mkdtemp(prefix="fqc-onboarding-pack-")
        )
        cls.db_path = cls.tmpdir / "fresh.db"

        from app import create_app

        cls.app = create_app({
            "TESTING": True,
            "ENVIRONMENT": "development",
            "IS_PRODUCTION": False,
            "SECRET_KEY": "test-secret-key-that-is-long-enough-12345",
            "DATABASE_PATH": cls.db_path,
            "BACKUP_DIRECTORY": cls.tmpdir / "backups",
            "SESSION_COOKIE_SECURE": False,
            "REGISTRATION_MODE": "local",
        })

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def setUp(self):
        # Recreate a truly fresh installation for each onboarding scenario.
        self.app.extensions.pop("unused", None)

        connection = sqlite3.connect(self.db_path)
        try:
            tables = [
                row[0]
                for row in connection.execute(
                    """
                    SELECT name
                    FROM sqlite_master
                    WHERE type='table'
                      AND name NOT LIKE 'sqlite_%'
                    """
                )
            ]

            connection.execute("PRAGMA foreign_keys=OFF")

            for table in tables:
                connection.execute(f'DELETE FROM "{table}"')

            connection.commit()
        finally:
            connection.close()

        # Re-run startup foundation so empty reference/system tables are valid.
        from services.multifamily_foundation import (
            ensure_multifamily_foundation,
        )
        from services.default_achievements import (
            ensure_core_achievements,
        )
        from services.onboarding import ensure_onboarding_schema

        ensure_multifamily_foundation(self.db_path)
        ensure_core_achievements(self.db_path)
        ensure_onboarding_schema(self.db_path)

        # Empty-family onboarding skips pack installation, so initialize the
        # pack tracking schema explicitly before asserting that it has no rows.
        from services.content_packs import ensure_content_pack_tables

        with self.app.app_context():
            ensure_content_pack_tables()

    def _csrf_from(self, client, path: str) -> str:
        response = client.get(path)
        self.assertEqual(response.status_code, 200)

        match = re.search(
            rb'name="csrf_token" value="([^"]+)"',
            response.data,
        )
        self.assertIsNotNone(match)

        return match.group(1).decode()

    def _setup_application_owner(self, client):
        token = self._csrf_from(client, "/account/setup-owner")
        response = client.post(
            "/account/setup-owner",
            data={
                "csrf_token": token,
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

    def _register(self, starter_experience: str):
        client = self.app.test_client()
        self._setup_application_owner(client)
        token = self._csrf_from(client, "/account/register")

        response = client.post(
            "/account/register",
            data={
                "csrf_token": token,
                "family_name": "Starter Test Family",
                "display_name": "Starter Parent",
                "email": f"{starter_experience}@example.com",
                "password": "StarterPassword123",
                "confirm_password": "StarterPassword123",
                "starter_experience": starter_experience,
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        return response

    def test_default_family_pack_uses_canonical_manifest_path(self):
        canonical_manifest = (
            ROOT
            / "content"
            / "packs"
            / "explorer_starter_pack"
            / "pack.json"
        )
        legacy_manifest = (
            ROOT
            / "content"
            / "default_pack"
            / "pack.json"
        )

        self.assertTrue(canonical_manifest.exists())

        # The legacy manifest may remain temporarily, but it must be a separate
        # file and must not replace the canonical Explorer Starter manifest.
        if legacy_manifest.exists():
            self.assertNotEqual(
                legacy_manifest.resolve(),
                canonical_manifest.resolve(),
            )

        manifest = json.loads(
            canonical_manifest.read_text(encoding="utf-8")
        )

        self.assertEqual(manifest["id"], "explorer_starter")
        self.assertEqual(manifest["name"], "Explorer Starter Pack")
        self.assertEqual(manifest.get("pack_type"), "core")
        self.assertFalse(manifest.get("archive_allowed", True))

    def test_selected_default_pack_installs_during_registration(self):
        self._register("explorer_starter")

        db = sqlite3.connect(self.db_path)
        try:
            family_id = db.execute(
                "SELECT id FROM families ORDER BY id LIMIT 1"
            ).fetchone()[0]

            installation = db.execute(
                """
                SELECT status
                FROM family_content_packs
                WHERE family_id=?
                  AND pack_key='explorer_starter'
                """,
                (family_id,),
            ).fetchone()

            self.assertIsNotNone(installation)
            self.assertEqual(installation[0], "active")

            self.assertGreater(
                db.execute(
                    "SELECT COUNT(*) FROM chores WHERE family_id=?",
                    (family_id,),
                ).fetchone()[0],
                0,
            )

            self.assertGreater(
                db.execute(
                    """
                    SELECT COUNT(*)
                    FROM adventures_v2
                    WHERE family_id=?
                    """,
                    (family_id,),
                ).fetchone()[0],
                0,
            )

            self.assertGreater(
                db.execute(
                    "SELECT COUNT(*) FROM rewards WHERE family_id=?",
                    (family_id,),
                ).fetchone()[0],
                0,
            )
        finally:
            db.close()

    def test_empty_family_does_not_install_default_pack(self):
        self._register("empty")

        db = sqlite3.connect(self.db_path)
        try:
            self.assertEqual(
                db.execute(
                    "SELECT COUNT(*) FROM family_content_packs"
                ).fetchone()[0],
                0,
            )

            self.assertEqual(
                db.execute(
                    "SELECT COUNT(*) FROM chores"
                ).fetchone()[0],
                0,
            )

            adventures_table_exists = db.execute(
                """
                SELECT 1
                FROM sqlite_master
                WHERE type='table'
                  AND name='adventures_v2'
                """
            ).fetchone()

            if adventures_table_exists:
                self.assertEqual(
                    db.execute(
                        "SELECT COUNT(*) FROM adventures_v2"
                    ).fetchone()[0],
                    0,
                )

            self.assertEqual(
                db.execute(
                    "SELECT COUNT(*) FROM rewards"
                ).fetchone()[0],
                0,
            )
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)