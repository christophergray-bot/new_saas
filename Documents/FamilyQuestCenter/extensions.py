"""Shared Flask extensions for hosted database management.

The existing application continues to use ``database.get_db()`` while the
hosted migration is completed module by module.  Flask-SQLAlchemy owns the
SQLAlchemy engine and Flask-Migrate/Alembic own schema versioning.
"""

from __future__ import annotations

from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base for hosted models added during persistence migration."""


orm_db = SQLAlchemy(model_class=Base, session_options={"expire_on_commit": False})
migrate = Migrate(compare_type=True, render_as_batch=True)


def init_extensions(app) -> None:
    """Initialize database and migration extensions for an application."""
    orm_db.init_app(app)
    migrate.init_app(app, orm_db, directory="db_migrations")
