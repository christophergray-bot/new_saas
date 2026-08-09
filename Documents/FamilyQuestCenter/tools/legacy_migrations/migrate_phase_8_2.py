"""Safely add Phase 8.2 achievement tables and starter data."""

from pathlib import Path
import sqlite3


BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = BASE_DIR / "chorce.db"
MIGRATION_PATH = BASE_DIR / "migrations" / "add_achievements.sql"


def main() -> None:
    """Handle the main workflow."""
    if not DATABASE_PATH.exists():
        raise SystemExit(
            "chorce.db was not found. Place this file in the main Chorce folder "
            "beside chorce.db, then run it again."
        )

    migration_sql = MIGRATION_PATH.read_text(encoding="utf-8")

    connection = sqlite3.connect(DATABASE_PATH)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(migration_sql)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

    print("Phase 8.2 achievement migration completed successfully.")


if __name__ == "__main__":
    main()
