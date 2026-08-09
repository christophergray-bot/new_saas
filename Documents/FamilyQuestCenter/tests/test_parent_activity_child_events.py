"""Regression coverage for FC-0032 child lifecycle Parent Activity."""
import os
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


class ParentActivityChildEventsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir=Path(tempfile.mkdtemp(prefix="fqc-parent-child-events-"))
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
            cls.account_id=int(row[0])
            cls.family_id=int(row[1])
            cls.auth_version=int(row[2] or 0)
        finally:
            connection.close()

        from app import create_app
        cls.app=create_app({
            "TESTING":True,
            "ENVIRONMENT":"development",
            "IS_PRODUCTION":False,
            "SECRET_KEY":"test-secret-key-that-is-long-enough-12345",
            "DATABASE_PATH":cls.db_path,
            "SESSION_COOKIE_SECURE":False,
        })

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmpdir,ignore_errors=True)

    def _parent_client(self):
        client=self.app.test_client()
        with client.session_transaction() as session:
            session["account_user_id"]=self.account_id
            session["family_id"]=self.family_id
            session["auth_version"]=self.auth_version
            session["parent_authenticated"]=True
        return client

    def _csrf(self,client):
        client.get("/parent/children/")
        with client.session_transaction() as session:
            return session["csrf_token"]

    def test_child_create_archive_restore_appear_in_reports_activity(self):
        client=self._parent_client()
        token=self._csrf(client)

        response=client.post(
            "/parent/children/add",
            data={"name":"Lifecycle Explorer","initial":"L","csrf_token":token},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code,302)

        connection=sqlite3.connect(self.db_path)
        try:
            child_id=connection.execute(
                "SELECT id FROM users WHERE family_id=? AND name='Lifecycle Explorer'",
                (self.family_id,),
            ).fetchone()[0]
        finally:
            connection.close()

        token=self._csrf(client)
        response=client.post(
            f"/parent/children/{child_id}/toggle",
            data={"csrf_token":token},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code,302)

        token=self._csrf(client)
        response=client.post(
            f"/parent/archive/children/child/{child_id}/restore",
            data={"csrf_token":token},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code,302)

        reports=client.get("/parent/reports/")
        self.assertEqual(reports.status_code,200)
        rendered=reports.get_data(as_text=True)
        self.assertIn("Lifecycle Explorer",rendered)
        self.assertIn("Child profile created",rendered)
        self.assertIn("Child profile archived",rendered)
        self.assertIn("Child profile restored",rendered)

    def test_other_family_child_events_are_not_displayed(self):
        connection=sqlite3.connect(self.db_path)
        try:
            other_family=connection.execute(
                "INSERT INTO families(name,slug,status) VALUES('Other Event Family','other-event-family','active')"
            ).lastrowid
            connection.execute(
                """INSERT INTO audit_log
                   (family_id,actor_type,actor_name,action,entity_type,entity_id,details)
                   VALUES(?, 'parent','Other Parent','child_created','child',999,'Hidden Explorer')""",
                (other_family,),
            )
            connection.commit()
        finally:
            connection.close()

        rendered=self._parent_client().get("/parent/reports/").get_data(as_text=True)
        self.assertNotIn("Hidden Explorer",rendered)


if __name__=="__main__":
    unittest.main()
