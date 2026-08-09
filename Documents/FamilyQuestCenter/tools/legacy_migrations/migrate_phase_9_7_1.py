"""Family Quest Center developer documentation.

File: tools/legacy_migrations/migrate_phase_9_7_1.py
Purpose: Supports the migrate phase 9 7 1 portion of Family Quest Center.

Maintenance notes:
- Preserve tenant and family data isolation when changing queries.
- Keep route, template, and schema changes synchronized.
- Run regression tests before release packaging.
Documentation updated: 2026-07-31.
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).with_name("chorce.db")

with sqlite3.connect(DB_PATH) as db:
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS notification_dismissals (
            notification_key TEXT PRIMARY KEY,
            dismissed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    db.commit()
print("Phase 9.7.1 migration complete.")
