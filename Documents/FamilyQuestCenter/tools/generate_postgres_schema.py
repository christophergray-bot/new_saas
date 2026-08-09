"""Generate a PostgreSQL schema from the current clean SQLite schema.

Run only from a trusted developer database with no customer data. This exports
DDL, not table rows.
"""
from pathlib import Path
import re
import sqlite3

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "chorce.db"
TARGET = ROOT / "schema_postgres.sql"


def convert(sql: str) -> str:
    sql = re.sub(r"INTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT", "BIGSERIAL PRIMARY KEY", sql, flags=re.I)
    sql = re.sub(r"\s+COLLATE\s+NOCASE", "", sql, flags=re.I)
    sql = re.sub(r"\bAUTOINCREMENT\b", "", sql, flags=re.I)
    sql = sql.replace('"', '"')
    return sql.rstrip() + ";"


def main():
    db = sqlite3.connect(SOURCE)
    objects = db.execute("""
        SELECT type, name, sql FROM sqlite_master
        WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%'
          AND type IN ('table','index')
        ORDER BY CASE type WHEN 'table' THEN 0 ELSE 1 END, rowid
    """).fetchall()
    lines = ["-- Generated PostgreSQL schema for Family Quest Center", "BEGIN;"]
    for object_type, name, sql in objects:
        if object_type == "index" and sql is None:
            continue
        lines.append(convert(sql))
    lines.append("COMMIT;")
    TARGET.write_text("\n\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {TARGET}")


if __name__ == "__main__":
    main()
