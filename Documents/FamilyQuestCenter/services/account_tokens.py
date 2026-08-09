"""Secure one-time tokens for password recovery, Parent PIN recovery, and invitations."""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin, urlsplit, urlunsplit

from flask import current_app

from database import get_db, is_postgres


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat(timespec="seconds")


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def ensure_account_token_schema() -> None:
    """Create recovery tables for both local SQLite and hosted PostgreSQL."""
    db = get_db()
    account_columns = {row["name"] for row in db.execute("PRAGMA table_info(account_users)").fetchall()}
    if "auth_version" not in account_columns:
        db.execute("ALTER TABLE account_users ADD COLUMN auth_version INTEGER NOT NULL DEFAULT 0")

    # SQLite's AUTOINCREMENT syntax is not valid in PostgreSQL.  Password
    # recovery is a public route, so this schema must be created using the
    # active database engine rather than relying on the SQLite compatibility
    # adapter to translate engine-specific DDL.
    if is_postgres():
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS password_reset_tokens (
                id BIGSERIAL PRIMARY KEY,
                account_user_id BIGINT NOT NULL,
                token_hash TEXT NOT NULL UNIQUE,
                expires_at TEXT NOT NULL,
                used_at TEXT,
                requested_ip TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(account_user_id) REFERENCES account_users(id)
            );
            CREATE INDEX IF NOT EXISTS idx_password_reset_account
                ON password_reset_tokens(account_user_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_password_reset_expiry
                ON password_reset_tokens(expires_at);
            CREATE TABLE IF NOT EXISTS pin_reset_tokens (
                id BIGSERIAL PRIMARY KEY,
                account_user_id BIGINT NOT NULL,
                family_id BIGINT NOT NULL,
                token_hash TEXT NOT NULL UNIQUE,
                expires_at TEXT NOT NULL,
                used_at TEXT,
                requested_ip TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(account_user_id) REFERENCES account_users(id),
                FOREIGN KEY(family_id) REFERENCES families(id)
            );
            CREATE INDEX IF NOT EXISTS idx_pin_reset_account
                ON pin_reset_tokens(account_user_id, family_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_pin_reset_expiry
                ON pin_reset_tokens(expires_at);
            """
        )
    else:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS password_reset_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_user_id INTEGER NOT NULL,
                token_hash TEXT NOT NULL UNIQUE,
                expires_at TEXT NOT NULL,
                used_at TEXT,
                requested_ip TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(account_user_id) REFERENCES account_users(id)
            );
            CREATE INDEX IF NOT EXISTS idx_password_reset_account
                ON password_reset_tokens(account_user_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_password_reset_expiry
                ON password_reset_tokens(expires_at);
            CREATE TABLE IF NOT EXISTS pin_reset_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_user_id INTEGER NOT NULL,
                family_id INTEGER NOT NULL,
                token_hash TEXT NOT NULL UNIQUE,
                expires_at TEXT NOT NULL,
                used_at TEXT,
                requested_ip TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(account_user_id) REFERENCES account_users(id),
                FOREIGN KEY(family_id) REFERENCES families(id)
            );
            CREATE INDEX IF NOT EXISTS idx_pin_reset_account
                ON pin_reset_tokens(account_user_id, family_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_pin_reset_expiry
                ON pin_reset_tokens(expires_at);
            """
        )
    db.commit()


def application_url(path: str = "") -> str:
    """Build an absolute application link from the configured site origin.

    APP_URL is intended to be the public site address, but hosted settings can
    accidentally contain a page such as ``/account/login``.  Using that value
    directly can produce links under the login path.  Keep only the scheme and
    host so recovery and invitation links always point to their real routes.
    """
    configured = str(current_app.config.get("APP_URL", "")).strip()
    if not configured:
        configured = "http://127.0.0.1:5000"

    parsed = urlsplit(configured)
    if not parsed.scheme or not parsed.netloc:
        configured = "http://127.0.0.1:5000"
        parsed = urlsplit(configured)

    origin = urlunsplit((parsed.scheme, parsed.netloc, "", "", "")).rstrip("/")
    return urljoin(origin + "/", path.lstrip("/"))


def create_password_reset_token(account_id: int, *, requested_ip: str | None = None, lifetime_minutes: int = 60) -> str:
    ensure_account_token_schema()
    db = get_db()
    now = _utc_now()
    db.execute(
        "UPDATE password_reset_tokens SET used_at=? WHERE account_user_id=? AND used_at IS NULL",
        (_iso(now), int(account_id)),
    )
    raw = secrets.token_urlsafe(32)
    db.execute(
        """INSERT INTO password_reset_tokens
           (account_user_id, token_hash, expires_at, requested_ip)
           VALUES (?, ?, ?, ?)""",
        (int(account_id), _hash_token(raw), _iso(now + timedelta(minutes=lifetime_minutes)), requested_ip),
    )
    db.commit()
    return raw


def get_valid_password_reset(token: str):
    ensure_account_token_schema()
    if not token:
        return None
    row = get_db().execute(
        """SELECT prt.id, prt.account_user_id, prt.expires_at, prt.used_at,
                  au.email, au.display_name, au.active
           FROM password_reset_tokens prt
           JOIN account_users au ON au.id=prt.account_user_id
           WHERE prt.token_hash=?""",
        (_hash_token(token),),
    ).fetchone()
    if row is None or row["used_at"] or not row["active"]:
        return None
    try:
        expires = datetime.fromisoformat(row["expires_at"])
    except (TypeError, ValueError):
        return None
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    return row if expires > _utc_now() else None


def consume_password_reset(token: str, password_hash: str) -> int | None:
    row = get_valid_password_reset(token)
    if row is None:
        return None
    db = get_db()
    now = _iso(_utc_now())
    db.execute(
        """UPDATE account_users
           SET password_hash=?, auth_version=auth_version+1, updated_at=CURRENT_TIMESTAMP
           WHERE id=?""",
        (password_hash, row["account_user_id"]),
    )
    db.execute(
        "UPDATE password_reset_tokens SET used_at=? WHERE account_user_id=? AND used_at IS NULL",
        (now, row["account_user_id"]),
    )
    db.commit()
    return int(row["account_user_id"])



def create_pin_reset_token(
    account_id: int,
    family_id: int,
    *,
    requested_ip: str | None = None,
    lifetime_minutes: int = 30,
) -> str:
    """Create one single-use Parent PIN recovery token."""
    ensure_account_token_schema()
    db = get_db()
    now = _utc_now()
    db.execute(
        """UPDATE pin_reset_tokens
           SET used_at=?
           WHERE account_user_id=? AND family_id=? AND used_at IS NULL""",
        (_iso(now), int(account_id), int(family_id)),
    )
    raw = secrets.token_urlsafe(32)
    db.execute(
        """INSERT INTO pin_reset_tokens
           (account_user_id, family_id, token_hash, expires_at, requested_ip)
           VALUES (?, ?, ?, ?, ?)""",
        (
            int(account_id),
            int(family_id),
            _hash_token(raw),
            _iso(now + timedelta(minutes=lifetime_minutes)),
            requested_ip,
        ),
    )
    db.commit()
    return raw


def get_valid_pin_reset(token: str):
    """Return a valid, unused Parent PIN recovery request."""
    ensure_account_token_schema()
    if not token:
        return None
    row = get_db().execute(
        """SELECT prt.id, prt.account_user_id, prt.family_id,
                  prt.expires_at, prt.used_at,
                  au.email, au.display_name, au.active
           FROM pin_reset_tokens prt
           JOIN account_users au ON au.id=prt.account_user_id
           JOIN family_memberships fm
             ON fm.account_user_id=prt.account_user_id
            AND fm.family_id=prt.family_id
            AND fm.role='owner'
            AND fm.active=1
           JOIN families f
             ON f.id=prt.family_id
            AND f.status='active'
           WHERE prt.token_hash=?""",
        (_hash_token(token),),
    ).fetchone()
    if row is None or row["used_at"] or not row["active"]:
        return None
    try:
        expires = datetime.fromisoformat(row["expires_at"])
    except (TypeError, ValueError):
        return None
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    return row if expires > _utc_now() else None


def consume_pin_reset(token: str) -> tuple[int, int] | None:
    """Consume a PIN recovery token and return account and family IDs."""
    row = get_valid_pin_reset(token)
    if row is None:
        return None
    db = get_db()
    result = db.execute(
        """UPDATE pin_reset_tokens
           SET used_at=?
           WHERE id=? AND used_at IS NULL""",
        (_iso(_utc_now()), row["id"]),
    )
    db.commit()
    if getattr(result, "rowcount", 1) == 0:
        return None
    return int(row["account_user_id"]), int(row["family_id"])

def hash_invitation_token(token: str) -> str:
    return _hash_token(token)
