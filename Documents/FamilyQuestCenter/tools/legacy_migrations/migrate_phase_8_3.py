"""Safe, repeatable Phase 8.3 migration."""
import sqlite3
from pathlib import Path

DATABASE = Path(__file__).resolve().parent / "chorce.db"
COLUMNS = {
    "avatar_key": "TEXT NOT NULL DEFAULT 'adventurer'",
    "title_key": "TEXT NOT NULL DEFAULT 'adventurer'",
    "frame_key": "TEXT NOT NULL DEFAULT 'bronze'",
    "theme_key": "TEXT NOT NULL DEFAULT 'quest'",
}

with sqlite3.connect(DATABASE) as connection:
    existing = {row[1] for row in connection.execute("PRAGMA table_info(users)")}
    for name, definition in COLUMNS.items():
        if name not in existing:
            connection.execute(f"ALTER TABLE users ADD COLUMN {name} {definition}")
    connection.commit()

print("Phase 8.3 character customization migration completed successfully.")
