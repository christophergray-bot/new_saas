"""Regression coverage for MGMT-0004 family Adventures Completed statistic."""
import os
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ManagementFamilyAdventureStatsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="fqc-mgmt-family-adventure-stats-"))
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
            # The baseline database already contains the current adventure
            # tables. Avoid ensure_journey_tables(), which correctly requires
            # an active family/request context.
            from database import get_db
            db = get_db()

            cls.owner_id = db.execute(
                """INSERT INTO account_users
                   (email,password_hash,display_name,email_verified,active,
                    platform_role,auth_version)
                   VALUES('adventure-stat-owner@example.com','unused',
                          'Adventure Stat Owner',1,1,'application_owner',0)"""
            ).lastrowid

            cls.family_a = db.execute(
                "INSERT INTO families(name,slug,status) VALUES('Adventure Stats A','adventure-stats-a','active')"
            ).lastrowid
            cls.family_b = db.execute(
                "INSERT INTO families(name,slug,status) VALUES('Adventure Stats B','adventure-stats-b','active')"
            ).lastrowid

            # Reuse actual schema dynamically by inserting only required columns.
            child_a = db.execute(
                """INSERT INTO users(name,initial,role,active,family_id)
                   VALUES('Explorer A','A','child',1,?)""",
                (cls.family_a,),
            ).lastrowid
            child_b = db.execute(
                """INSERT INTO users(name,initial,role,active,family_id)
                   VALUES('Explorer B','B','child',1,?)""",
                (cls.family_b,),
            ).lastrowid

            adv_a = db.execute(
                """INSERT INTO adventures_v2(name,description,bonus_xp,active,family_id)
                   VALUES('Adventure A','Test',1,1,?)""",
                (cls.family_a,),
            ).lastrowid
            adv_b = db.execute(
                """INSERT INTO adventures_v2(name,description,bonus_xp,active,family_id)
                   VALUES('Adventure B','Test',1,1,?)""",
                (cls.family_b,),
            ).lastrowid

            # Two completed adventures for A, one for B, plus one active A
            # instance that must not count as completed.
            for _ in range(2):
                db.execute(
                    """INSERT INTO adventure_instances_v2
                       (adventure_id,child_id,status,start_date,completed_at,family_id)
                       VALUES(?,?,'completed',CURRENT_DATE,CURRENT_TIMESTAMP,?)""",
                    (adv_a, child_a, cls.family_a),
                )
            db.execute(
                """INSERT INTO adventure_instances_v2
                   (adventure_id,child_id,status,start_date,family_id)
                   VALUES(?,?,'active',CURRENT_DATE,?)""",
                (adv_a, child_a, cls.family_a),
            )
            db.execute(
                """INSERT INTO adventure_instances_v2
                   (adventure_id,child_id,status,start_date,completed_at,family_id)
                   VALUES(?,?,'completed',CURRENT_DATE,CURRENT_TIMESTAMP,?)""",
                (adv_b, child_b, cls.family_b),
            )
            db.commit()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def test_manage_family_counts_completed_v2_adventures_for_selected_family(self):
        client = self.app.test_client()
        with client.session_transaction() as session:
            session["account_user_id"] = int(self.owner_id)
            session["auth_version"] = 0

        response = client.get(f"/developer/families/{self.family_a}")
        self.assertEqual(response.status_code, 200)
        rendered = response.get_data(as_text=True)
        self.assertIn("<span>Adventures Completed</span><strong>2</strong>", rendered)


if __name__ == "__main__":
    unittest.main()
