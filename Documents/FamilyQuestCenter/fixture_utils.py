"""Small deterministic fixtures for regression tests.

These helpers operate only on each test's temporary SQLite copy.  They prevent
regression tests from depending on whichever families/users happen to exist in
the developer's working ``chorce.db``. Tests use ``tests/fixtures/baseline.db``
as an immutable sanitized baseline instead of the developer database.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path


def ensure_primary_family_fixture(db_path: str | Path) -> tuple[int, int]:
    """Ensure account 1 can act as Parent One for family 1 in a temp test DB."""
    connection = sqlite3.connect(db_path)
    connection.execute("PRAGMA foreign_keys=ON")
    try:
        family = connection.execute("SELECT id FROM families WHERE id=1").fetchone()
        if family is None:
            connection.execute(
                "INSERT INTO families(id,name,slug,status) VALUES(1,?,?, 'active')",
                ("Test Family One", "test-family-one"),
            )
        else:
            connection.execute("UPDATE families SET status='active' WHERE id=1")

        account = connection.execute("SELECT id FROM account_users WHERE id=1").fetchone()
        if account is None:
            connection.execute(
                """INSERT INTO account_users
                   (id,email,password_hash,display_name,email_verified,active,platform_role,auth_version)
                   VALUES(1,'test-owner-one@example.invalid','test-only-password-hash',
                          'Test Owner One',1,1,'application_owner',0)"""
            )
        else:
            connection.execute("UPDATE account_users SET active=1 WHERE id=1")

        membership = connection.execute(
            "SELECT id FROM family_memberships WHERE family_id=1 AND account_user_id=1"
        ).fetchone()
        if membership is None:
            connection.execute(
                "INSERT INTO family_memberships(family_id,account_user_id,role,active) VALUES(1,1,'owner',1)"
            )
        else:
            connection.execute(
                "UPDATE family_memberships SET role='owner', active=1 WHERE family_id=1 AND account_user_id=1"
            )

        security = connection.execute(
            "SELECT family_id FROM family_security WHERE family_id=1"
        ).fetchone()
        if security is None:
            source_hash = connection.execute(
                "SELECT parent_pin_hash FROM family_security WHERE parent_pin_hash IS NOT NULL LIMIT 1"
            ).fetchone()
            # Werkzeug accepts this pbkdf2 hash format; the actual PIN value is
            # irrelevant to tests that replace/reset the hash.
            pin_hash = (
                source_hash[0]
                if source_hash
                else "pbkdf2:sha256:1$test$5e884898da28047151d0e56f8dc6292773603d0d6aabbdd62a11ef721d1542d8"
            )
            connection.execute(
                "INSERT INTO family_security(family_id,parent_pin_hash) VALUES(1,?)",
                (pin_hash,),
            )

        child = connection.execute(
            "SELECT id FROM users WHERE family_id=1 AND role='child' AND active=1 ORDER BY id LIMIT 1"
        ).fetchone()
        if child is None:
            connection.execute(
                """INSERT INTO users
                   (name,role,initial,active,total_points,total_xp,current_level,current_streak,
                    avatar_key,title_key,frame_key,theme_key,family_id)
                   VALUES('Test Child One','child','T',1,0,0,1,0,
                          'adventurer','adventurer','bronze','quest',1)"""
            )

        connection.commit()
        return 1, 1
    finally:
        connection.close()


def ensure_secondary_family_fixture(db_path: str | Path) -> tuple[int, int]:
    """Return an active non-primary parent/family pair, creating one if needed."""
    connection = sqlite3.connect(db_path)
    connection.execute("PRAGMA foreign_keys=ON")
    try:
        row = connection.execute(
            """SELECT fm.account_user_id, fm.family_id
               FROM family_memberships fm
               JOIN account_users au ON au.id=fm.account_user_id
               JOIN families f ON f.id=fm.family_id
               WHERE fm.active=1 AND au.active=1 AND f.status='active'
                 AND fm.family_id<>1 AND fm.account_user_id<>1
               ORDER BY fm.family_id, fm.account_user_id LIMIT 1"""
        ).fetchone()
        if row:
            return int(row[0]), int(row[1])

        family_id = int(connection.execute(
            "INSERT INTO families(name,slug,status) VALUES('Test Family Two','test-family-two','active')"
        ).lastrowid)
        account_id = int(connection.execute(
            """INSERT INTO account_users
               (email,password_hash,display_name,email_verified,active,platform_role,auth_version)
               VALUES('test-owner-two@example.invalid','test-only-password-hash',
                      'Test Owner Two',1,1,'none',0)"""
        ).lastrowid)
        connection.execute(
            "INSERT INTO family_memberships(family_id,account_user_id,role,active) VALUES(?,?,'owner',1)",
            (family_id, account_id),
        )
        connection.commit()
        return account_id, family_id
    finally:
        connection.close()
