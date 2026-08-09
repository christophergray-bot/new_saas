"""Idempotent database repair for family-scoped Mission Builder schedules."""
from __future__ import annotations

from contextlib import closing

import sqlite3
from pathlib import Path


def _column_exists(connection: sqlite3.Connection, table: str, column: str) -> bool:
    """Handle the column exists workflow."""
    return any(row[1] == column for row in connection.execute(f'PRAGMA table_info("{table}")'))


def ensure_mission_tenant_isolation(database_path: str | Path) -> None:
    """Add, repair, and index quest_schedules.family_id safely.

    Existing schedules are assigned to a family only when their selected child
    and quest belong to the same family. Ambiguous cross-family schedules are
    disabled rather than exposed to either tenant.
    """
    with closing(sqlite3.connect(Path(database_path))) as connection, connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        if "quest_schedules" not in tables:
            return

        if not _column_exists(connection, "quest_schedules", "family_id"):
            connection.execute(
                "ALTER TABLE quest_schedules ADD COLUMN family_id INTEGER"
            )

        # Repair schedules using both ownership anchors. This corrects records
        # created before Mission Builder writes stored family_id.
        connection.execute(
            """
            UPDATE quest_schedules
            SET family_id = (
                SELECT u.family_id
                FROM users u
                JOIN chores c ON c.id = quest_schedules.chore_id
                WHERE u.id = quest_schedules.child_id
                  AND u.family_id = c.family_id
                  AND u.family_id IS NOT NULL
            )
            WHERE EXISTS (
                SELECT 1
                FROM users u
                JOIN chores c ON c.id = quest_schedules.chore_id
                WHERE u.id = quest_schedules.child_id
                  AND u.family_id = c.family_id
                  AND u.family_id IS NOT NULL
            )
            """
        )

        # Never run an ambiguous schedule. It can be recreated by the correct
        # family after the conflicting child/quest selection is corrected.
        connection.execute(
            """
            UPDATE quest_schedules
            SET active = 0
            WHERE family_id IS NULL
               OR NOT EXISTS (
                    SELECT 1
                    FROM users u
                    JOIN chores c ON c.id = quest_schedules.chore_id
                    WHERE u.id = quest_schedules.child_id
                      AND u.family_id = quest_schedules.family_id
                      AND c.family_id = quest_schedules.family_id
               )
            """
        )

        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_quest_schedules_family_active "
            "ON quest_schedules(family_id, active, start_date, end_date)"
        )
        connection.commit()
