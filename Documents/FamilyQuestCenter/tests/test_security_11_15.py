import os, shutil, sqlite3, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

from tests.fixture_utils import ensure_primary_family_fixture

class Security1115Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix='fqc-security-'))
        cls.db_path = cls.tmpdir / 'test.db'
        shutil.copy2(ROOT / 'tests' / 'fixtures' / 'baseline.db', cls.db_path)
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

    def client_for(self, account_id=None, family_id=None, unlocked=False):
        client = self.app.test_client()
        if account_id:
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

            with client.session_transaction() as session:
                session["account_user_id"] = account_id
                session["family_id"] = family_id
                session["auth_version"] = auth_version
                session["csrf_token"] = "test-token"
                if unlocked:
                    session["parent_authenticated"] = True
        return client

    def test_unauthenticated_parent_redirects_to_account_login(self):
        r = self.app.test_client().get('/parent/')
        self.assertEqual(r.status_code, 302)
        self.assertIn('/account/login', r.location)

    def test_owner_without_pin_unlock_redirects_to_parent_login(self):
        r = self.client_for(1, 1, False).get('/parent/')
        self.assertEqual(r.status_code, 302)
        self.assertIn('/parent/login', r.location)

    def test_owner_with_pin_unlock_reaches_parent_area(self):
        r = self.client_for(1, 1, True).get('/parent/')
        self.assertIn(r.status_code, (200, 302))
        self.assertNotIn('/parent/login', r.location or '')
        self.assertNotIn('/account/login', r.location or '')

    def test_caregiver_is_forbidden_from_parent_area(self):
        db = sqlite3.connect(self.db_path)
        db.execute("UPDATE family_memberships SET role='caregiver' WHERE account_user_id=1 AND family_id=1")
        db.commit(); db.close()
        try:
            r = self.client_for(1, 1, True).get('/parent/')
            self.assertEqual(r.status_code, 403)
        finally:
            db = sqlite3.connect(self.db_path)
            db.execute("UPDATE family_memberships SET role='owner' WHERE account_user_id=1 AND family_id=1")
            db.commit(); db.close()

    def test_cross_family_child_id_returns_not_found(self):
        r = self.client_for(1, 1, True).get('/parent/children/3')
        self.assertEqual(r.status_code, 404)

    def test_oversized_common_field_is_rejected(self):
        client = self.client_for(1, 1, True)
        r = client.post('/parent/children/add', data={
            'csrf_token': 'test-token', 'name': 'A' * 101, 'initial': 'A'
        })
        self.assertEqual(r.status_code, 400)

    def test_forgot_pin_link_is_available_at_pin_gate(self):
        r = self.client_for(1, 1, False).get('/parent/login')
        self.assertEqual(r.status_code, 200)
        self.assertIn(b'Reset PIN by Email', r.data)

    def test_unauthenticated_pin_reset_redirects_to_account_login(self):
        r = self.app.test_client().get('/parent/reset-pin')
        self.assertEqual(r.status_code, 302)
        self.assertIn('/account/login', r.location)

    def test_owner_can_reset_forgotten_pin_by_email(self):
        import re
        from urllib.parse import urlsplit
        from unittest.mock import patch
        from werkzeug.security import check_password_hash

        db = sqlite3.connect(self.db_path)
        old_pin = db.execute(
            "SELECT parent_pin_hash FROM family_security WHERE family_id=1"
        ).fetchone()[0]
        db.close()

        try:
            client = self.client_for(1, 1, False)
            with patch("routes.auth.send_email") as mocked_send:
                response = client.post(
                    "/parent/reset-pin",
                    data={"csrf_token": "test-token"},
                    follow_redirects=False,
                )

            self.assertEqual(response.status_code, 302)
            mocked_send.assert_called_once()
            text_body = mocked_send.call_args.kwargs["text_body"]
            match = re.search(r"https?://[^\s]+/parent/reset-pin/[^\s]+", text_body)
            self.assertIsNotNone(match, "Recovery email did not contain a reset link")
            reset_path = urlsplit(match.group(0)).path

            reset_page = client.get(reset_path)
            self.assertEqual(reset_page.status_code, 200)
            self.assertIn(b"Create a New Parent PIN", reset_page.data)

            with client.session_transaction() as session:
                session["csrf_token"] = "test-token"

            completed = client.post(
                reset_path,
                data={
                    "csrf_token": "test-token",
                    "new_pin": "2468",
                    "confirm_pin": "2468",
                },
                follow_redirects=False,
            )
            self.assertEqual(completed.status_code, 302)

            with client.session_transaction() as session:
                self.assertTrue(session.get("parent_authenticated"))

            db = sqlite3.connect(self.db_path)
            new_pin_hash = db.execute(
                "SELECT parent_pin_hash FROM family_security WHERE family_id=1"
            ).fetchone()[0]
            db.close()
            self.assertTrue(check_password_hash(new_pin_hash, "2468"))

            reused = client.get(reset_path, follow_redirects=False)
            self.assertEqual(reused.status_code, 302)
        finally:
            db = sqlite3.connect(self.db_path)
            db.execute(
                "UPDATE family_security SET parent_pin_hash=? WHERE family_id=1",
                (old_pin,),
            )
            db.commit()
            db.close()

if __name__ == '__main__':
    unittest.main(verbosity=2)
