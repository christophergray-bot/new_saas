"""Shared database access for local SQLite and hosted PostgreSQL.

The public ``get_db()`` interface remains intentionally small so routes and
models do not need to know which database engine is active.
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

from flask import current_app, g

try:
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import Engine
except ImportError:  # Local startup provides a clearer error only if PG is selected.
    create_engine = None
    text = None
    Engine = Any


class HybridRow(Mapping):
    """Row object supporting both ``row[0]`` and ``row['column']`` access."""

    def __init__(self, keys: list[str], values: tuple[Any, ...]):
        self._keys = keys
        self._values = values
        self._mapping = dict(zip(keys, values))

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._values[key]
        return self._mapping[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._keys)

    def __len__(self) -> int:
        return len(self._keys)

    def keys(self):
        return self._mapping.keys()


class ResultAdapter:
    def __init__(self, result=None, *, synthetic_rows=None, lastrowid=None):
        self._result = result
        self._synthetic_rows = list(synthetic_rows or [])
        self.lastrowid = lastrowid

    def _convert(self, row):
        if row is None or isinstance(row, HybridRow):
            return row
        mapping = row._mapping
        return HybridRow(list(mapping.keys()), tuple(mapping.values()))

    def fetchone(self):
        if self._synthetic_rows:
            return self._synthetic_rows.pop(0)
        return self._convert(self._result.fetchone()) if self._result is not None else None

    def fetchall(self):
        if self._synthetic_rows:
            rows, self._synthetic_rows = self._synthetic_rows, []
            return rows
        return [self._convert(row) for row in self._result.fetchall()] if self._result is not None else []

    @property
    def rowcount(self):
        return self._result.rowcount if self._result is not None else 0


class PostgresConnectionAdapter:
    """Small DB-API compatibility layer over SQLAlchemy for existing raw SQL."""

    def __init__(self, engine: Engine):
        self.engine = engine
        self.connection = engine.connect()
        self.transaction = self.connection.begin()
        self._table_id_cache: dict[str, bool] = {}

    def _table_has_id(self, table: str) -> bool:
        if table not in self._table_id_cache:
            row = self.connection.execute(
                text("""
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema='public' AND table_name=:table AND column_name='id'
                """),
                {"table": table},
            ).first()
            self._table_id_cache[table] = row is not None
        return self._table_id_cache[table]

    @staticmethod
    def _replace_qmarks(sql: str, params) -> tuple[str, dict[str, Any]]:
        values = tuple(params or ())
        output, bind, index, quote = [], {}, 0, None
        for char in sql:
            if char in {"'", '"'}:
                if quote is None:
                    quote = char
                elif quote == char:
                    quote = None
                output.append(char)
            elif char == "?" and quote is None:
                name = f"p{index}"
                output.append(f":{name}")
                bind[name] = values[index]
                index += 1
            else:
                output.append(char)
        if index != len(values):
            raise ValueError(f"SQL parameter mismatch: expected {index}, received {len(values)}")
        return "".join(output), bind

    def _pragma_result(self, sql: str):
        normalized = sql.strip().rstrip(";")
        match = re.match(r'PRAGMA\s+table_info\(["\']?([^"\')]+)', normalized, re.I)
        if match:
            table_name = match.group(1)
            result = self.connection.execute(text("""
                SELECT
                    (ordinal_position - 1) AS cid,
                    column_name AS name,
                    data_type AS type,
                    CASE WHEN is_nullable='NO' THEN 1 ELSE 0 END AS notnull,
                    column_default AS dflt_value,
                    CASE WHEN column_name IN (
                        SELECT kcu.column_name
                        FROM information_schema.table_constraints tc
                        JOIN information_schema.key_column_usage kcu
                          ON tc.constraint_name=kcu.constraint_name
                         AND tc.table_schema=kcu.table_schema
                        WHERE tc.table_schema='public' AND tc.table_name=:table
                          AND tc.constraint_type='PRIMARY KEY'
                    ) THEN 1 ELSE 0 END AS pk
                FROM information_schema.columns
                WHERE table_schema='public' AND table_name=:table
                ORDER BY ordinal_position
            """), {"table": table_name})
            return ResultAdapter(result)
        if re.match(r"PRAGMA\s+integrity_check", normalized, re.I):
            return ResultAdapter(synthetic_rows=[HybridRow(["integrity_check"], ("ok",))])
        if re.match(r"PRAGMA\s+foreign_key_check", normalized, re.I):
            return ResultAdapter(synthetic_rows=[])
        if re.match(r"PRAGMA\s+(foreign_keys|busy_timeout)", normalized, re.I):
            return ResultAdapter(synthetic_rows=[HybridRow(["value"], (1,))])
        return None

    def _translate_sqlite_master(self, sql: str, params):
        lower = sql.lower()
        if "sqlite_master" not in lower:
            return None
        if "type='table'" in lower or 'type = \'table\'' in lower:
            if "name not like 'sqlite_%'" in lower:
                pg_sql = "SELECT tablename AS name FROM pg_catalog.pg_tables WHERE schemaname='public'"
                return pg_sql, {}
            if "name" in lower and ("name=?" in lower.replace(" ", "") or "name = ?" in lower):
                _, bind = self._replace_qmarks("SELECT 1 FROM pg_catalog.pg_tables WHERE schemaname='public' AND tablename=?", params)
                return "SELECT 1 FROM pg_catalog.pg_tables WHERE schemaname='public' AND tablename=:p0", bind
            literal = re.search(r"name\s*=\s*'([^']+)'", sql, re.I)
            if literal:
                return "SELECT 1 FROM pg_catalog.pg_tables WHERE schemaname='public' AND tablename=:table", {"table": literal.group(1)}
            return "SELECT tablename AS name FROM pg_catalog.pg_tables WHERE schemaname='public'", {}
        return None

    def execute(self, sql: str, params=()):
        pragma = self._pragma_result(sql)
        if pragma is not None:
            return pragma

        master = self._translate_sqlite_master(sql, params)
        if master is not None:
            pg_sql, bind = master
            return ResultAdapter(self.connection.execute(text(pg_sql), bind))

        translated = re.sub(r"\s+COLLATE\s+NOCASE", "", sql, flags=re.I)
        ignore = bool(re.match(r"\s*INSERT\s+OR\s+IGNORE\s+INTO", translated, re.I))
        translated = re.sub(r"\bINSERT\s+OR\s+IGNORE\s+INTO\b", "INSERT INTO", translated, flags=re.I)
        if ignore and "ON CONFLICT" not in translated.upper():
            translated = translated.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"

        if re.match(r"\s*INSERT\s+OR\s+REPLACE", translated, re.I):
            raise RuntimeError("INSERT OR REPLACE must be converted to an explicit PostgreSQL upsert.")

        table_match = re.match(r"\s*INSERT\s+INTO\s+[\"']?([A-Za-z_][A-Za-z0-9_]*)", translated, re.I)
        wants_returning = False
        if table_match and "RETURNING" not in translated.upper() and self._table_has_id(table_match.group(1)):
            translated = translated.rstrip().rstrip(";") + " RETURNING id"
            wants_returning = True

        translated, bind = self._replace_qmarks(translated, params)
        result = self.connection.execute(text(translated), bind)
        lastrowid = None
        if wants_returning:
            row = result.first()
            lastrowid = row[0] if row else None
            return ResultAdapter(None, lastrowid=lastrowid)
        return ResultAdapter(result)

    def executemany(self, sql: str, parameter_rows):
        result = None
        for params in parameter_rows:
            result = self.execute(sql, params)
        return result or ResultAdapter()

    def executescript(self, script: str):
        for statement in script.split(";"):
            if statement.strip():
                self.execute(statement)
        return self

    def commit(self):
        if self.transaction.is_active:
            self.transaction.commit()
        self.transaction = self.connection.begin()

    def rollback(self):
        if self.transaction.is_active:
            self.transaction.rollback()
        self.transaction = self.connection.begin()

    def close(self):
        if self.transaction.is_active:
            self.transaction.rollback()
        self.connection.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self.commit()
        else:
            self.rollback()
        self.close()


_engine: Engine | None = None


def is_postgres() -> bool:
    return bool(current_app.config.get("DATABASE_URL"))


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        if create_engine is None:
            raise RuntimeError("SQLAlchemy and psycopg are required when DATABASE_URL is configured.")
        url = current_app.config["DATABASE_URL"]
        if url.startswith("postgres://"):
            url = "postgresql+psycopg://" + url[len("postgres://"):]
        elif url.startswith("postgresql://"):
            url = "postgresql+psycopg://" + url[len("postgresql://"):]
        _engine = create_engine(url, pool_pre_ping=True, pool_recycle=300)
    return _engine


def get_db():
    if "db" not in g:
        if is_postgres():
            g.db = PostgresConnectionAdapter(get_engine())
        else:
            database_path = current_app.config["DATABASE_PATH"]
            g.db = sqlite3.connect(database_path)
            g.db.row_factory = sqlite3.Row
            g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(exception=None):
    database = g.pop("db", None)
    if database is not None:
        database.close()


def init_app(app):
    app.teardown_appcontext(close_db)
