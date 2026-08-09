"""Family Quest Center developer documentation.

File: init_db.py
Purpose: Initializes the Family Quest Center database schema and required seed configuration.

Maintenance notes:
- Preserve tenant and family data isolation when changing queries.
- Keep route, template, and schema changes synchronized.
- Run regression tests before release packaging.
Documentation updated: 2026-07-31.
"""

from contextlib import closing
from pathlib import Path
import sqlite3


BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = BASE_DIR / "chorce.db"
SCHEMA_PATH = BASE_DIR / "schema.sql"


def initialize_database(database_path=None) -> None:
    """Create a fresh Family Quest Center database from ``schema.sql``.

    When ``database_path`` is omitted, the normal local database is used.
    Tests and alternate installations should pass an explicit path.
    """
    target_path = Path(database_path) if database_path is not None else DATABASE_PATH

    if not SCHEMA_PATH.exists():
        raise FileNotFoundError(
            f"Database schema was not found: {SCHEMA_PATH}"
        )

    schema = SCHEMA_PATH.read_text(encoding="utf-8")

    target_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(target_path)) as connection, connection:
        connection.executescript(schema)

    from services.multifamily_foundation import ensure_multifamily_foundation
    ensure_multifamily_foundation(target_path)

    print(f"Chorce database created successfully:")
    print(target_path)


if __name__ == "__main__":
    initialize_database()

def initialize_postgres_database(engine) -> None:
    """Create the hosted PostgreSQL schema when the database is empty."""
    schema_path = BASE_DIR / "schema_postgres.sql"
    if not schema_path.exists():
        raise FileNotFoundError(f"PostgreSQL schema was not found: {schema_path}")

    from sqlalchemy import text
    with engine.begin() as connection:
        table_count = connection.execute(
            text("SELECT COUNT(*) FROM pg_catalog.pg_tables WHERE schemaname='public'")
        ).scalar_one()
        if table_count:
            return
        schema = schema_path.read_text(encoding="utf-8")
        for statement in schema.split(";"):
            if statement.strip() and statement.strip().upper() not in {"BEGIN", "COMMIT"}:
                connection.exec_driver_sql(statement)
