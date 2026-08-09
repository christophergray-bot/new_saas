"""Regression coverage for MGMT-0007 Manage Families installed packs."""
import os
import shutil
import sqlite3
import tempfile
import unittest
import html
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ManagementFamilyPacksTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="fqc-mgmt-family-packs-"))
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
        })

        with cls.app.app_context():
            from services.content_packs import ensure_content_pack_tables
            ensure_content_pack_tables()

            from database import get_db
            db = get_db()
            cls.owner_id = db.execute(
                """INSERT INTO account_users
                   (email,password_hash,display_name,email_verified,active,
                    platform_role,auth_version)
                   VALUES('family-pack-owner@example.com','unused',
                          'Family Pack Owner',1,1,'application_owner',0)"""
            ).lastrowid
            cls.family_a = db.execute(
                "INSERT INTO families(name,slug,status) VALUES('Pack Family A','pack-family-a','active')"
            ).lastrowid
            cls.family_b = db.execute(
                "INSERT INTO families(name,slug,status) VALUES('Pack Family B','pack-family-b','active')"
            ).lastrowid
            # Use canonical catalog packs registered by the application.
            catalog_rows = db.execute(
                "SELECT pack_key,name,version FROM content_packs WHERE active=1 ORDER BY pack_key"
            ).fetchall()
            if not catalog_rows:
                raise RuntimeError("No canonical content packs were registered")

            pack_a = catalog_rows[0]
            pack_b = catalog_rows[1] if len(catalog_rows) > 1 else catalog_rows[0]

            db.execute(
                """INSERT INTO family_content_packs
                   (family_id,pack_key,installed_version,status)
                   VALUES(?,?,?,'active')""",
                (cls.family_a, pack_a["pack_key"], pack_a["version"]),
            )
            if pack_b["pack_key"] != pack_a["pack_key"]:
                db.execute(
                    """INSERT INTO family_content_packs
                       (family_id,pack_key,installed_version,status)
                       VALUES(?,?,?,'active')""",
                    (cls.family_b, pack_b["pack_key"], pack_b["version"]),
                )
            cls.pack_a_name = pack_a["name"]
            cls.pack_a_version = str(pack_a["version"])
            cls.pack_b_name = pack_b["name"] if pack_b["pack_key"] != pack_a["pack_key"] else None
            db.commit()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def test_manage_family_shows_only_selected_family_installed_packs(self):
        client = self.app.test_client()
        with client.session_transaction() as session:
            session["account_user_id"] = int(self.owner_id)
            session["auth_version"] = 0

        response = client.get(f"/developer/families/{self.family_a}")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Installed Packs", response.data)
        rendered = html.unescape(response.get_data(as_text=True))
        self.assertIn(self.pack_a_name, rendered)
        self.assertIn(f"Version {self.pack_a_version}", rendered)
        if self.pack_b_name:
            self.assertNotIn(self.pack_b_name, rendered)


if __name__ == "__main__":
    unittest.main()
