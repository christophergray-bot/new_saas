"""Multi-family database foundation for the hosted edition.

This module is deliberately backward compatible with the local single-family
application. It creates tenant/account tables, creates one default family for
existing data, and adds ``family_id`` to family-owned records. Existing routes
continue to work while later sprints add authentication and mandatory tenant
scoping.
"""

from __future__ import annotations

from contextlib import closing

import sqlite3
from pathlib import Path

FAMILY_OWNED_TABLES = (
    "users",
    "chores",
    "assignments",
    "quest_schedules",
    "quest_chains",
    "quest_chain_instances",
    "family_challenges",
    "journeys",
    "journey_instances",
    "adventures_v2",
    "adventure_instances_v2",
    "adventure_schedules",
    "adventure_schedule_occurrences",
    "rewards",
    "reward_categories",
    "reward_requests",
    "reward_history",
    "star_transactions",
    "point_history",
    "xp_history",
    "user_achievements",
    "notification_dismissals",
)


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    """Handle the table exists workflow."""
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?",
        (table_name,),
    ).fetchone() is not None


def _column_exists(
    connection: sqlite3.Connection,
    table_name: str,
    column_name: str,
) -> bool:
    """Handle the column exists workflow."""
    if not _table_exists(connection, table_name):
        return False
    return any(
        row[1] == column_name
        for row in connection.execute(f'PRAGMA table_info("{table_name}")')
    )


def ensure_multifamily_foundation(database_path: str | Path) -> int:
    """Install the multi-family foundation and return the default family ID."""

    database_path = Path(database_path)
    with closing(sqlite3.connect(database_path)) as connection, connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS families (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                slug TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active', 'suspended', 'archived')),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS account_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL COLLATE NOCASE UNIQUE,
                password_hash TEXT NOT NULL,
                display_name TEXT NOT NULL,
                email_verified INTEGER NOT NULL DEFAULT 0
                    CHECK (email_verified IN (0, 1)),
                active INTEGER NOT NULL DEFAULT 1
                    CHECK (active IN (0, 1)),
                last_login_at TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS family_memberships (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                family_id INTEGER NOT NULL,
                account_user_id INTEGER NOT NULL,
                role TEXT NOT NULL DEFAULT 'parent'
                    CHECK (role IN ('owner', 'parent', 'caregiver')),
                active INTEGER NOT NULL DEFAULT 1
                    CHECK (active IN (0, 1)),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (family_id) REFERENCES families(id),
                FOREIGN KEY (account_user_id) REFERENCES account_users(id),
                UNIQUE (family_id, account_user_id)
            );

            CREATE INDEX IF NOT EXISTS idx_family_memberships_family
                ON family_memberships(family_id);
            CREATE INDEX IF NOT EXISTS idx_family_memberships_account
                ON family_memberships(account_user_id);
            """
        )

        family = connection.execute(
            "SELECT id FROM families ORDER BY id LIMIT 1"
        ).fetchone()
        if family is None:
            # Only create a compatibility family when upgrading legacy data. A
            # clean hosted installation must begin with the platform-only
            # Application Owner and no customer family.
            has_legacy_family_data = any(
                _table_exists(connection, table_name)
                and connection.execute(f'SELECT 1 FROM "{table_name}" LIMIT 1').fetchone() is not None
                for table_name in FAMILY_OWNED_TABLES
            )
            if has_legacy_family_data:
                family_name = "My Family"
                if _table_exists(connection, "settings"):
                    row = connection.execute(
                        "SELECT value FROM settings WHERE key = 'family_name'"
                    ).fetchone()
                    if row and str(row[0]).strip():
                        family_name = str(row[0]).strip()
                cursor = connection.execute(
                    "INSERT INTO families (name, slug) VALUES (?, ?)",
                    (family_name, "default-family"),
                )
                default_family_id = int(cursor.lastrowid)
            else:
                default_family_id = 0
        else:
            default_family_id = int(family[0])

        for table_name in FAMILY_OWNED_TABLES:
            if not _table_exists(connection, table_name):
                continue
            if not _column_exists(connection, table_name, "family_id"):
                connection.execute(
                    f'ALTER TABLE "{table_name}" ADD COLUMN family_id INTEGER'
                )
            if default_family_id:
                connection.execute(
                    f'UPDATE "{table_name}" SET family_id = ? WHERE family_id IS NULL',
                    (default_family_id,),
                )
            connection.execute(
                f'CREATE INDEX IF NOT EXISTS "idx_{table_name}_family_id" '
                f'ON "{table_name}" (family_id)'
            )

        if _table_exists(connection, "migration_history"):
            connection.execute(
                """
                INSERT OR IGNORE INTO migration_history
                    (version, description, status)
                VALUES (?, ?, 'success')
                """,
                (
                    "3.0-A",
                    "Multi-family database and account foundation",
                ),
            )

        # Platform roles are independent from family memberships. Normal family
        # accounts use ``none``; the first installation account uses
        # ``application_owner`` and does not require a family membership.
        if not _column_exists(connection, "account_users", "platform_role"):
            connection.execute(
                "ALTER TABLE account_users ADD COLUMN platform_role TEXT NOT NULL DEFAULT 'none'"
            )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_account_users_platform_role "
            "ON account_users(platform_role)"
        )

        connection.commit()
        return default_family_id
