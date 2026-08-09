"""Tenant-safe settings access for Family Quest Center."""
from __future__ import annotations

from flask import has_request_context

from database import get_db

DEFAULT_SETTINGS = {
    "application_name": "Family Quest Center",
    "family_name": "Our Family",
    "default_quest_difficulty": "1",
    "default_quest_stars": "1",
    "default_approval_required": "1",
    "daily_reset_time": "04:00",
    "streak_grace_days": "3",
    "session_timeout_minutes": "600",  # legacy compatibility
    "session_timeout_seconds": "600",
    "child_session_timeout_seconds": "43200",
    "xp_difficulty_1": "1",
    "xp_difficulty_2": "2",
    "xp_difficulty_3": "4",
    "xp_difficulty_4": "8",
    "xp_difficulty_5": "16",
    "family_timezone": "America/Los_Angeles",
    "family_country": "United States",
    "family_date_format": "MM/DD/YYYY",
    "registration_mode": "local",
}

GLOBAL_SETTING_KEYS = {
    "registration_mode", "installation_owner_account_id",
    "system_application_name", "company_name", "support_email", "contact_website",
    "require_email_verification", "default_trial_days", "default_starter_pack",
    "billing_enabled", "trial_enabled", "subscription_grace_days", "default_plan",
    "platform_session_timeout_minutes", "maximum_login_attempts", "account_lockout_minutes",
    "remember_me_days", "parent_pin_min_length", "maintenance_mode",
    "maintenance_allow_registration", "maintenance_message",
}
FAMILY_SETTING_KEYS = set(DEFAULT_SETTINGS) - GLOBAL_SETTING_KEYS


def ensure_settings_table() -> None:
    db = get_db()
    db.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    db.execute(
        """CREATE TABLE IF NOT EXISTS family_settings (
            family_id INTEGER NOT NULL,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (family_id, key),
            FOREIGN KEY (family_id) REFERENCES families(id) ON DELETE CASCADE
        )"""
    )
    db.execute("CREATE INDEX IF NOT EXISTS idx_family_settings_family ON family_settings(family_id)")
    db.commit()


def _current_family_id() -> int | None:
    if not has_request_context():
        return None
    try:
        from services.tenant_context import get_current_family_id
        return int(get_current_family_id())
    except (RuntimeError, TypeError, ValueError):
        return None


def ensure_default_settings() -> None:
    ensure_settings_table()
    db = get_db()

    # Only installation-wide settings belong in the global settings table.
    global_defaults = {
        key: value
        for key, value in DEFAULT_SETTINGS.items()
        if key in GLOBAL_SETTING_KEYS
    }
    db.executemany(
        "INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)",
        global_defaults.items(),
    )

    # New families receive the current application defaults directly.
    # Existing family-specific values are preserved by INSERT OR IGNORE.
    family_id = _current_family_id()
    if family_id is not None:
        values = [
            (family_id, key, DEFAULT_SETTINGS[key])
            for key in FAMILY_SETTING_KEYS
        ]
        db.executemany(
            "INSERT OR IGNORE INTO family_settings(family_id,key,value) VALUES(?,?,?)",
            values,
        )

    db.commit()

def get_global_setting(key: str, default=None):
    ensure_settings_table()
    row = get_db().execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return default if row is None else row["value"]


def set_global_setting(key: str, value: str) -> None:
    ensure_settings_table()
    db = get_db()
    db.execute(
        "INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, str(value)),
    )
    db.commit()


def get_family_setting(key: str, default=None, family_id: int | None = None):
    ensure_settings_table()
    family_id = family_id if family_id is not None else _current_family_id()
    if family_id is None:
        return default

    row = get_db().execute(
        "SELECT value FROM family_settings WHERE family_id=? AND key=?",
        (family_id, key),
    ).fetchone()

    if row is not None:
        return row["value"]

    return default

def set_family_setting(key: str, value: str, family_id: int | None = None) -> None:
    family_id = family_id if family_id is not None else _current_family_id()
    if family_id is None:
        raise RuntimeError("A family context is required to update family settings.")
    ensure_settings_table()
    db = get_db()
    db.execute(
        """INSERT INTO family_settings(family_id,key,value,updated_at)
           VALUES(?,?,?,CURRENT_TIMESTAMP)
           ON CONFLICT(family_id,key) DO UPDATE SET value=excluded.value,updated_at=CURRENT_TIMESTAMP""",
        (family_id, key, str(value)),
    )
    db.commit()


def set_family_settings(values: dict[str, str], family_id: int | None = None) -> None:
    family_id = family_id if family_id is not None else _current_family_id()
    if family_id is None:
        raise RuntimeError("A family context is required to update family settings.")
    ensure_settings_table()
    db = get_db()
    db.executemany(
        """INSERT INTO family_settings(family_id,key,value,updated_at)
           VALUES(?,?,?,CURRENT_TIMESTAMP)
           ON CONFLICT(family_id,key) DO UPDATE SET value=excluded.value,updated_at=CURRENT_TIMESTAMP""",
        [(family_id, key, str(value)) for key, value in values.items()],
    )
    db.commit()


def get_setting(key: str, default=None):
    if key in GLOBAL_SETTING_KEYS:
        return get_global_setting(key, default)
    return get_family_setting(key, default)


def set_setting(key: str, value: str) -> None:
    if key in GLOBAL_SETTING_KEYS:
        set_global_setting(key, value)
    else:
        set_family_setting(key, value)


def set_settings(values: dict[str, str]) -> None:
    global_values = {k: v for k, v in values.items() if k in GLOBAL_SETTING_KEYS}
    family_values = {k: v for k, v in values.items() if k not in GLOBAL_SETTING_KEYS}
    for key, value in global_values.items():
        set_global_setting(key, value)
    if family_values:
        set_family_settings(family_values)


def get_int_setting(key: str, default: int) -> int:
    try:
        return int(get_setting(key, default))
    except (TypeError, ValueError):
        return default


def get_bool_setting(key: str, default: bool = False) -> bool:
    return str(get_setting(key, "1" if default else "0")).strip().lower() in {"1", "true", "yes", "on"}


def get_public_settings() -> dict[str, object]:
    ensure_default_settings()
    family_id = _current_family_id()
    family_name = DEFAULT_SETTINGS["family_name"]
    if family_id is not None:
        row = get_db().execute("SELECT name FROM families WHERE id=?", (family_id,)).fetchone()
        if row is not None:
            family_name = row["name"]
    return {
        "application_name": get_family_setting("application_name", DEFAULT_SETTINGS["application_name"]),
        "family_name": family_name,
        "default_quest_difficulty": get_int_setting("default_quest_difficulty", 1),
        "default_quest_stars": get_int_setting("default_quest_stars", 1),
        "default_approval_required": get_bool_setting("default_approval_required", True),
        "daily_reset_time": get_setting("daily_reset_time", "04:00"),
        "streak_grace_days": get_int_setting("streak_grace_days", 3),
        "session_timeout_seconds": get_int_setting("session_timeout_seconds", get_int_setting("session_timeout_minutes", 600)),
        "child_session_timeout_seconds": get_int_setting("child_session_timeout_seconds", 43200),
        "xp_difficulty_1": get_int_setting("xp_difficulty_1", 1),
        "xp_difficulty_2": get_int_setting("xp_difficulty_2", 2),
        "xp_difficulty_3": get_int_setting("xp_difficulty_3", 4),
        "xp_difficulty_4": get_int_setting("xp_difficulty_4", 8),
        "xp_difficulty_5": get_int_setting("xp_difficulty_5", 16),
    }


def parent_pin_exists() -> bool:
    from services.family_security import parent_pin_exists as family_pin_exists
    return family_pin_exists()


def get_xp_for_difficulty(difficulty: int) -> int:
    try:
        difficulty = min(max(int(difficulty), 1), 5)
    except (TypeError, ValueError):
        difficulty = 1
    defaults = {1: 1, 2: 2, 3: 4, 4: 8, 5: 16}
    return max(get_int_setting(f"xp_difficulty_{difficulty}", defaults[difficulty]), 0)


REGISTRATION_MODES = {"local", "closed", "open", "trial"}

def get_registration_mode(config_default: str = "local") -> str:
    value = str(get_global_setting("registration_mode", config_default)).strip().lower()
    return value if value in REGISTRATION_MODES else config_default


def registration_is_enabled(config_default: str = "local") -> bool:
    return get_registration_mode(config_default) in {"local", "open", "trial"}
