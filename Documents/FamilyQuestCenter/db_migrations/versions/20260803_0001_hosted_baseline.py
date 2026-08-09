"""Create the hosted PostgreSQL baseline schema.

Revision ID: 20260803_0001
Revises: None
Create Date: 2026-08-03
"""
from __future__ import annotations

from pathlib import Path

from alembic import op
from sqlalchemy import inspect

revision = "20260803_0001"
down_revision = None
branch_labels = None
depends_on = None


def _split_sql(script: str):
    # The generated baseline contains ordinary DDL and no procedural bodies.
    for statement in script.split(";"):
        statement = statement.strip()
        if statement and statement.upper() not in {"BEGIN", "COMMIT"}:
            yield statement


def upgrade():
    bind = op.get_bind()
    dialect = bind.dialect.name

    # Local SQLite continues to use schema.sql and the established migration
    # services. Alembic stamps it so developers can use the same CLI safely.
    if dialect == "sqlite":
        return
    if dialect != "postgresql":
        raise RuntimeError(f"Unsupported hosted database dialect: {dialect}")

    existing = set(inspect(bind).get_table_names())
    application_tables = existing - {"alembic_version"}
    if application_tables:
        raise RuntimeError(
            "The PostgreSQL baseline migration requires an empty database. "
            f"Found existing tables: {', '.join(sorted(application_tables))}"
        )

    schema_path = Path(__file__).resolve().parents[2] / "schema_postgres.sql"
    script = schema_path.read_text(encoding="utf-8")
    for statement in _split_sql(script):
        bind.exec_driver_sql(statement)


def downgrade():
    raise RuntimeError(
        "The hosted baseline cannot be downgraded automatically. Restore a "
        "managed PostgreSQL backup instead."
    )
