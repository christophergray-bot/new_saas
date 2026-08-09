"""Per-family shared-device parent PIN storage."""
from __future__ import annotations

from database import get_db
from services.tenant_context import get_current_family_id


def ensure_family_security_table() -> None:
    """Handle the ensure family security table workflow."""
    db = get_db()
    db.execute(
        """CREATE TABLE IF NOT EXISTS family_security (
            family_id INTEGER PRIMARY KEY,
            parent_pin_hash TEXT,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (family_id) REFERENCES families(id)
        )"""
    )
    # Preserve the legacy PIN for the migrated default family only.
    legacy = db.execute("SELECT value FROM settings WHERE key='parent_pin_hash'").fetchone()
    default_family = db.execute("SELECT id FROM families WHERE slug='default-family'").fetchone()
    if legacy and default_family:
        db.execute(
            "INSERT OR IGNORE INTO family_security(family_id,parent_pin_hash) VALUES(?,?)",
            (default_family["id"], legacy["value"] if hasattr(legacy, "keys") else legacy[0]),
        )
    db.commit()


def get_parent_pin_hash() -> str | None:
    """Retrieve parent pin hash."""
    ensure_family_security_table()
    row = get_db().execute(
        "SELECT parent_pin_hash FROM family_security WHERE family_id=?",
        (get_current_family_id(),),
    ).fetchone()
    return row[0] if row else None


def parent_pin_exists() -> bool:
    """Handle the parent pin exists workflow."""
    return bool(get_parent_pin_hash())


def set_parent_pin_hash(value: str) -> None:
    """Handle the set parent pin hash workflow."""
    ensure_family_security_table()
    db = get_db()
    db.execute(
        """INSERT INTO family_security(family_id,parent_pin_hash,updated_at)
           VALUES(?,?,CURRENT_TIMESTAMP)
           ON CONFLICT(family_id) DO UPDATE SET parent_pin_hash=excluded.parent_pin_hash,updated_at=CURRENT_TIMESTAMP""",
        (get_current_family_id(), value),
    )
    db.commit()
