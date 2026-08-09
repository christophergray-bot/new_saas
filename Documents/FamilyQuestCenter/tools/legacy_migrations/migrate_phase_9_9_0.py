"""Record the Phase 9.9 reliability release. Safe to run more than once."""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "chorce.db"
MIGRATION = "phase_9_9_0"
VERSION = "0.9.9.0"

with sqlite3.connect(DB_PATH) as db:
    db.execute("CREATE TABLE IF NOT EXISTS application_info (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    db.execute("CREATE TABLE IF NOT EXISTS migration_history (id INTEGER PRIMARY KEY AUTOINCREMENT, migration_name TEXT NOT NULL UNIQUE, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
    already = db.execute("SELECT 1 FROM migration_history WHERE migration_name=?", (MIGRATION,)).fetchone()
    if already:
        print("Phase 9.9.0 migration already applied.")
    else:
        db.execute("INSERT INTO migration_history (migration_name) VALUES (?)", (MIGRATION,))
        for key in ("version", "application_version", "database_version"):
            db.execute("INSERT INTO application_info(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, VERSION))
        db.commit()
        print("Phase 9.9.0 migration completed.")
