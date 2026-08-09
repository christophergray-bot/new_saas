"""Run the Phase 8 migration without needing the sqlite3 command-line tool."""

from pathlib import Path
import sqlite3


PROJECT_DIR = Path(__file__).resolve().parent
DATABASE_PATH = PROJECT_DIR / "chorce.db"
MIGRATION_PATH = PROJECT_DIR / "migrations" / "add_character_progression.sql"


def column_exists(connection: sqlite3.Connection, table: str, column: str) -> bool:
    """Handle the column exists workflow."""
    rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row[1] == column for row in rows)


def main() -> None:
    """Handle the main workflow."""
    if not DATABASE_PATH.exists():
        raise SystemExit(
            f"Database not found at {DATABASE_PATH}. Copy this script into the "
            "main Chorce folder beside chorce.db, then run it again."
        )

    connection = sqlite3.connect(DATABASE_PATH)

    try:
        if column_exists(connection, "users", "total_xp"):
            print("Phase 8 migration has already been applied.")
            return

        migration_sql = MIGRATION_PATH.read_text(encoding="utf-8")
        connection.executescript(migration_sql)
        connection.commit()
        print("Phase 8 migration completed successfully.")
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


if __name__ == "__main__":
    main()
