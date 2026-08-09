"""Family Quest Center developer documentation.

File: tools/legacy_migrations/migrate_phase_9_5_2.py
Purpose: Supports the migrate phase 9 5 2 portion of Family Quest Center.

Maintenance notes:
- Preserve tenant and family data isolation when changing queries.
- Keep route, template, and schema changes synchronized.
- Run regression tests before release packaging.
Documentation updated: 2026-07-31.
"""

from pathlib import Path
import sqlite3

BASE_DIR = Path(__file__).resolve().parent
DATABASE = BASE_DIR / "chorce.db"
MIGRATION = BASE_DIR / "migrations" / "add_administration_diagnostics.sql"


def main():
    """Handle the main workflow."""
    if not DATABASE.exists():
        raise SystemExit("chorce.db was not found beside this migration script.")
    if not MIGRATION.exists():
        raise SystemExit("The Phase 9.5 Part 2 SQL migration file is missing.")

    with sqlite3.connect(DATABASE) as connection:
        connection.executescript(MIGRATION.read_text(encoding="utf-8"))
        connection.commit()

    print("Phase 9.5 Part 2 migration completed successfully.")
    print("Administration, diagnostics, audit logging, and error logging are ready.")


if __name__ == "__main__":
    main()
