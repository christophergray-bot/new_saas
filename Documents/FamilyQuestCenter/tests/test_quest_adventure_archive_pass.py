"""Regression coverage for Quest/Adventure archive placement and ADJ-0011."""
import os
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


class QuestAdventureArchivePassTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir=Path(tempfile.mkdtemp(prefix="fqc-quest-adventure-pass-"))
        cls.db_path=cls.tmpdir/"test.db"
        shutil.copy2(ROOT/"tests"/"fixtures"/"baseline.db",cls.db_path)
        os.chdir(ROOT)

        connection=sqlite3.connect(cls.db_path)
        try:
            row=connection.execute(
                """SELECT au.id,fm.family_id,COALESCE(au.auth_version,0)
                   FROM account_users au
                   JOIN family_memberships fm ON fm.account_user_id=au.id
                   JOIN families f ON f.id=fm.family_id
                   WHERE au.active=1 AND fm.active=1 AND f.status='active'
                     AND fm.role IN ('owner','parent')
                     AND COALESCE(au.platform_role,'none')<>'application_owner'
                   ORDER BY au.id LIMIT 1"""
            ).fetchone()
            if row is None:
                raise unittest.SkipTest("No ordinary Parent account in baseline")
            cls.account_id=int(row[0]); cls.family_id=int(row[1]); cls.auth_version=int(row[2] or 0)
            cls.quest_id=connection.execute(
                """INSERT INTO chores(title,description,difficulty,stars,approval_required,active,family_id)
                   VALUES('Archive Placement Quest','Test',1,1,1,1,?)""",
                (cls.family_id,),
            ).lastrowid
            connection.commit()
        finally:
            connection.close()

        from app import create_app
        cls.app=create_app({
            "TESTING":True,"ENVIRONMENT":"development","IS_PRODUCTION":False,
            "SECRET_KEY":"test-secret-key-that-is-long-enough-12345",
            "DATABASE_PATH":cls.db_path,"SESSION_COOKIE_SECURE":False,
        })
        with cls.app.test_request_context("/"):
            from flask import session
            session["account_user_id"]=cls.account_id
            session["family_id"]=cls.family_id
            session["auth_version"]=cls.auth_version
            session["parent_authenticated"]=True
            from models.journeys import ensure_journey_tables
            ensure_journey_tables()

        connection=sqlite3.connect(cls.db_path)
        try:
            cls.adventure_id=connection.execute(
                """INSERT INTO adventures_v2
                   (name,description,bonus_xp,approval_required,active,family_id)
                   VALUES('Archive Placement Adventure','Test',10,1,1,?)""",
                (cls.family_id,),
            ).lastrowid
            connection.commit()
        finally:
            connection.close()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmpdir,ignore_errors=True)

    def _client(self):
        client=self.app.test_client()
        with client.session_transaction() as session:
            session["account_user_id"]=self.account_id
            session["family_id"]=self.family_id
            session["auth_version"]=self.auth_version
            session["parent_authenticated"]=True
        return client

    def test_quest_library_has_no_archive_action_but_edit_does(self):
        client=self._client()
        library=client.get("/parent/quests/").get_data(as_text=True)
        self.assertIn(f"/parent/quests/{self.quest_id}/edit",library)
        self.assertNotIn(f"/parent/quests/{self.quest_id}/toggle",library)

        edit=client.get(f"/parent/quests/{self.quest_id}/edit").get_data(as_text=True)
        self.assertIn("<h2>Archive Quest</h2>",edit)
        self.assertIn("📦 Archive Quest",edit)

    def test_adventure_library_has_no_archive_action_but_edit_does(self):
        client=self._client()
        library=client.get("/parent/adventures").get_data(as_text=True)
        self.assertIn(f"/parent/adventures/{self.adventure_id}/edit",library)
        self.assertNotIn(f"/parent/adventures/{self.adventure_id}/toggle",library)

        edit=client.get(f"/parent/adventures/{self.adventure_id}/edit").get_data(as_text=True)
        self.assertIn("<h2>Archive Adventure</h2>",edit)
        self.assertIn("📦 Archive Adventure",edit)

    def test_locked_assigned_adventure_edit_also_shows_archive(self):
        connection=sqlite3.connect(self.db_path)
        try:
            child_id=connection.execute(
                "SELECT id FROM users WHERE family_id=? AND role='child' AND active=1 ORDER BY id LIMIT 1",
                (self.family_id,),
            ).fetchone()[0]
            connection.execute(
                """INSERT INTO adventure_instances_v2
                   (adventure_id,child_id,start_date,status,family_id)
                   VALUES(?,?,'2026-08-06','active',?)""",
                (self.adventure_id,child_id,self.family_id),
            )
            connection.commit()
        finally:
            connection.close()

        rendered=self._client().get(
            f"/parent/adventures/{self.adventure_id}/edit"
        ).get_data(as_text=True)
        self.assertIn("Adventure Locked",rendered)
        self.assertIn("<h2>Archive Adventure</h2>",rendered)
        self.assertIn("📦 Archive Adventure",rendered)

    def test_new_adventure_defaults_parent_approval_checked(self):
        rendered=self._client().get("/parent/adventures/new").get_data(as_text=True)
        self.assertRegex(
            rendered,
            r'name="approval_required"[^>]*checked',
        )
        self.assertIn("Requires Parent Approval",rendered)

    def test_adventure_approval_setting_is_saved(self):
        client=self._client()
        page=client.get("/parent/adventures/new")
        with client.session_transaction() as session:
            token=session["csrf_token"]
        response=client.post(
            "/parent/adventures/new",
            data={
                "csrf_token":token,
                "name":"No Approval Adventure",
                "description":"Test",
                "bonus_xp":"5",
                "chapter_id":"",
                "chapter_name":"One Step",
                "chapter_description":"Complete it",
                # approval_required intentionally omitted
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code,302)
        connection=sqlite3.connect(self.db_path)
        try:
            value=connection.execute(
                "SELECT approval_required FROM adventures_v2 WHERE family_id=? AND name='No Approval Adventure'",
                (self.family_id,),
            ).fetchone()[0]
        finally:
            connection.close()
        self.assertEqual(value,0)


if __name__=="__main__":
    unittest.main()
