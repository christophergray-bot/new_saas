"""Phase 9.8 migration: editable family and operational settings."""

from app import app
from database import get_db
from models.settings import ensure_default_settings


with app.app_context():
    ensure_default_settings()
    database = get_db()

    existing_tables = {
        row[0]
        for row in database.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }

    if "application_info" in existing_tables:
        database.execute(
            """
            INSERT INTO application_info (key, value)
            VALUES ('version', '0.9.8.0')
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """
        )

    if "migration_history" in existing_tables:
        already_recorded = database.execute(
            "SELECT 1 FROM migration_history WHERE version = ?",
            ("0.9.8.0",),
        ).fetchone()
        if not already_recorded:
            database.execute(
                """
                INSERT INTO migration_history (version, description, status)
                VALUES (?, ?, 'success')
                """,
                (
                    "0.9.8.0",
                    "Added editable family, quest-default, daily-rule, and session settings.",
                ),
            )

    database.commit()
    print("Phase 9.8 migration complete. Application version: 0.9.8.0")
