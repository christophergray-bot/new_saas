"""Family Quest Center developer documentation.

File: models/administration.py
Purpose: Provides database access and domain operations for administration data.

Maintenance notes:
- Preserve tenant and family data isolation when changing queries.
- Keep route, template, and schema changes synchronized.
- Run regression tests before release packaging.
Documentation updated: 2026-07-31.
"""

from __future__ import annotations

import json
import platform
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from flask import current_app

from database import get_db


_SENSITIVE_LOG_PATTERNS = (
    re.compile(r"(?i)(password|passphrase|pin|csrf(?:_token)?|session(?:_id)?|secret|token)\s*[:=]\s*([^\s,;]+)"),
    re.compile(r"(?i)(authorization|cookie)\s*[:=]\s*([^\r\n]+)"),
)

def sanitize_log_text(value: object | None, limit: int = 2000) -> str | None:
    """Redact common credentials and bound text before persistent logging."""
    if value is None:
        return None
    text = str(value).replace("\x00", "")
    for pattern in _SENSITIVE_LOG_PATTERNS:
        text = pattern.sub(lambda match: f"{match.group(1)}=[REDACTED]", text)
    return text[:limit]


def _ensure_audit_family_column() -> None:
    """Ensure audit records can be isolated by family."""
    db = get_db()
    columns = {row["name"] for row in db.execute("PRAGMA table_info(audit_log)").fetchall()}
    if "family_id" not in columns:
        db.execute("ALTER TABLE audit_log ADD COLUMN family_id INTEGER")
        db.execute("CREATE INDEX IF NOT EXISTS audit_log_family_index ON audit_log(family_id, created_at DESC)")
        db.commit()


def log_audit(action: str, entity_type: str | None = None, entity_id: int | None = None,
              details: str | None = None, actor_type: str = "parent", actor_name: str = "Parent") -> None:
    """Record an audit event and associate it with the active family when available."""
    db = get_db()
    _ensure_audit_family_column()
    family_id = None
    try:
        from services.account_auth import get_current_membership
        membership = get_current_membership()
        if membership is not None:
            family_id = int(membership["family_id"])
    except (RuntimeError, KeyError, TypeError, ValueError):
        family_id = None
    db.execute(
        """
        INSERT INTO audit_log
        (family_id, actor_type, actor_name, action, entity_type, entity_id, details)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (family_id, actor_type, sanitize_log_text(actor_name, 100), sanitize_log_text(action, 100),
         sanitize_log_text(entity_type, 100), entity_id, sanitize_log_text(details, 2000)),
    )
    db.commit()


def record_error(error_type: str, message: str, traceback_text: str | None = None,
                 request_path: str | None = None) -> None:
    """Handle the record error workflow."""
    try:
        db = get_db()
        db.execute(
            """
            INSERT INTO error_log (error_type, message, traceback_text, request_path)
            VALUES (?, ?, ?, ?)
            """,
            (sanitize_log_text(error_type, 100), sanitize_log_text(message, 1000),
             sanitize_log_text(traceback_text, 8000), sanitize_log_text(request_path, 500)),
        )
        db.commit()
    except Exception:
        current_app.logger.exception("Unable to write error to database")


def get_audit_entries(limit: int = 100, action: str | None = None, *, search: str | None = None,
                      category: str | None = None, start_date: str | None = None,
                      end_date: str | None = None):
    """Retrieve filtered, redacted audit entries for the Application Owner."""
    db = get_db()
    clauses: list[str] = []
    params: list[Any] = []
    if action:
        clauses.append("action = ?")
        params.append(action)
    if search:
        like = f"%{search.strip()}%"
        clauses.append("(action LIKE ? OR actor_name LIKE ? OR actor_type LIKE ? OR entity_type LIKE ? OR details LIKE ? OR CAST(entity_id AS TEXT) LIKE ? OR CAST(family_id AS TEXT) LIKE ?)")
        params.extend([like] * 7)
    category_map = {
        "family": ("family_%",), "parent": ("parent_%", "account_%", "password_%", "email_%"),
        "security": ("login_%", "security_%", "%lock%", "%logout%"),
        "backup": ("database_backup_%", "database_restore_%", "family_data_exported"),
        "settings": ("system_settings_%",), "subscription": ("subscription_%", "billing_%", "stripe_%"),
        "packs": ("pack_%", "content_pack_%"), "system": ("system_%", "email_test_%", "migration_%"),
    }
    patterns = category_map.get((category or "").lower())
    if patterns:
        clauses.append("(" + " OR ".join("action LIKE ?" for _ in patterns) + ")")
        params.extend(patterns)
    if start_date:
        clauses.append("date(created_at) >= date(?)")
        params.append(start_date)
    if end_date:
        clauses.append("date(created_at) <= date(?)")
        params.append(end_date)
    sql = "SELECT * FROM audit_log"
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY created_at DESC, id DESC LIMIT ?"
    params.append(limit)
    return db.execute(sql, params).fetchall()


def audit_summary() -> dict[str, int]:
    """Return compact audit counts for Operations and Audit Center."""
    db = get_db()
    return {
        "Today": db.execute("SELECT COUNT(*) FROM audit_log WHERE date(created_at)=date('now','localtime')").fetchone()[0],
        "Last 7 Days": db.execute("SELECT COUNT(*) FROM audit_log WHERE created_at >= datetime('now','-7 days')").fetchone()[0],
        "Owner Actions": db.execute("SELECT COUNT(*) FROM audit_log WHERE actor_type IN ('application_owner','installation_owner')").fetchone()[0],
        "Security Events": db.execute("SELECT COUNT(*) FROM audit_log WHERE action LIKE '%login%' OR action LIKE '%lock%' OR action LIKE '%password%' OR action LIKE '%security%'").fetchone()[0],
    }


def get_error_entries(limit: int = 100):
    """Retrieve error entries."""
    return get_db().execute(
        "SELECT * FROM error_log ORDER BY created_at DESC, id DESC LIMIT ?", (limit,)
    ).fetchall()


def clear_error_entries() -> int:
    """Handle the clear error entries workflow."""
    db = get_db()
    count = db.execute("SELECT COUNT(*) FROM error_log").fetchone()[0]
    db.execute("DELETE FROM error_log")
    db.commit()
    return count


def set_error_resolved(error_id: int, resolved: bool = True) -> bool:
    """Mark an application error resolved or unresolved."""
    db = get_db()
    result = db.execute("UPDATE error_log SET resolved=? WHERE id=?", (1 if resolved else 0, error_id))
    db.commit()
    return result.rowcount > 0


def get_migration_history():
    """Retrieve migration history."""
    return get_db().execute(
        "SELECT * FROM migration_history ORDER BY applied_at DESC, id DESC"
    ).fetchall()


def get_application_info() -> dict[str, str]:
    """Retrieve application info."""
    rows = get_db().execute("SELECT key, value FROM application_info").fetchall()
    return {row["key"]: row["value"] for row in rows}


def database_statistics() -> dict[str, int]:
    """Handle the database statistics workflow."""
    db = get_db()
    tables = {
        "Children": ("users", "role = 'child'"),
        "Parents": ("users", "role = 'parent'"),
        "Quest Templates": ("chores", None),
        "Assignments": ("assignments", None),
        "Rewards": ("rewards", None),
        "Reward Requests": ("reward_requests", None),
        "Achievements": ("achievements", None),
        "Achievement Unlocks": ("user_achievements", None),
        "XP Entries": ("xp_history", None),
        "Star Transactions": ("star_transactions", None),
        "Audit Entries": ("audit_log", None),
        "Error Entries": ("error_log", None),
    }
    existing = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    stats: dict[str, int] = {}
    for label, (table, where) in tables.items():
        if table not in existing:
            stats[label] = 0
            continue
        query = f"SELECT COUNT(*) FROM {table}"
        if where:
            query += f" WHERE {where}"
        stats[label] = db.execute(query).fetchone()[0]
    return stats



def platform_overview() -> dict[str, object]:
    """Return platform-level counts for the Application Owner dashboard."""
    db = get_db()
    existing = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}

    def scalar(sql: str, params: tuple = ()) -> int:
        try:
            row = db.execute(sql, params).fetchone()
            return int(row[0] or 0) if row else 0
        except sqlite3.Error:
            return 0

    total_families = scalar("SELECT COUNT(*) FROM families") if "families" in existing else 0
    active_families = scalar("SELECT COUNT(*) FROM families WHERE status='active'") if "families" in existing else 0
    suspended_families = scalar("SELECT COUNT(*) FROM families WHERE status='suspended'") if "families" in existing else 0
    parent_accounts = scalar(
        "SELECT COUNT(DISTINCT account_user_id) FROM family_memberships WHERE active=1 AND role IN ('owner','parent')"
    ) if "family_memberships" in existing else 0
    children = scalar("SELECT COUNT(*) FROM users WHERE role='child' AND active=1") if "users" in existing else 0
    active_subscriptions = scalar(
        "SELECT COUNT(DISTINCT family_id) FROM family_subscriptions WHERE status IN ('active','trialing')"
    ) if "family_subscriptions" in existing else 0
    trial_accounts = scalar(
        "SELECT COUNT(DISTINCT family_id) FROM family_subscriptions WHERE status='trialing'"
    ) if "family_subscriptions" in existing else 0

    return {
        "Total Families": total_families,
        "Active Families": active_families,
        "Parent Accounts": parent_accounts,
        "Children": children,
        "Active Subscriptions": active_subscriptions,
        "Trial Accounts": trial_accounts,
        "Suspended Families": suspended_families,
        "Monthly Revenue": "—",
    }


def platform_attention_items() -> list[dict[str, str]]:
    """Return owner-facing conditions that may need attention."""
    db = get_db()
    items: list[dict[str, str]] = []
    existing = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}

    if "error_log" in existing:
        unresolved = db.execute("SELECT COUNT(*) FROM error_log WHERE COALESCE(resolved,0)=0").fetchone()[0]
        if unresolved:
            items.append({"icon": "🚨", "title": f"{unresolved} unresolved application error{'s' if unresolved != 1 else ''}", "detail": "Review the Error Log.", "endpoint": "developer.errors"})

    if "family_subscriptions" in existing:
        past_due = db.execute("SELECT COUNT(DISTINCT family_id) FROM family_subscriptions WHERE status='past_due'").fetchone()[0]
        if past_due:
            items.append({"icon": "💳", "title": f"{past_due} past-due subscription{'s' if past_due != 1 else ''}", "detail": "Review subscription status.", "endpoint": "developer.subscriptions"})

    try:
        from services.email_service import email_configuration_status
        if not email_configuration_status().get("configured"):
            items.append({"icon": "✉️", "title": "Email is not fully configured", "detail": "Complete SMTP configuration before inviting families.", "endpoint": "developer.email_test"})
    except Exception:
        items.append({"icon": "✉️", "title": "Email status could not be verified", "detail": "Review Operations and email settings.", "endpoint": "developer.email_test"})

    try:
        from models.reliability import list_backups
        if not list_backups():
            items.append({"icon": "💾", "title": "No database backup is available", "detail": "Create the first backup before production use.", "endpoint": "maintenance.center"})
    except Exception:
        pass
    return items


def platform_health_summary() -> list[dict[str, str]]:
    """Build the compact health summary used on the owner dashboard."""
    from models.settings import get_registration_mode
    from services.email_service import email_configuration_status
    from models.reliability import list_backups

    app_info = get_application_info()
    db_path = Path(current_app.config["DATABASE_PATH"])
    checks = system_health()
    application_status = "Healthy" if all(item["status"] == "healthy" for item in checks) else "Warning"
    email_status = "Healthy" if email_configuration_status().get("configured") else "Not Configured"
    backups = list_backups()
    stripe_mode = str(current_app.config.get("PAYMENTS_MODE", "disabled")).replace("_", " ").title()
    return [
        {"label": "Application Status", "value": application_status, "status": application_status.lower().replace(" ", "-")},
        {"label": "Database Status", "value": "Healthy" if db_path.exists() else "Critical", "status": "healthy" if db_path.exists() else "critical"},
        {"label": "Database Size", "value": f"{db_path.stat().st_size / 1024:.1f} KB" if db_path.exists() else "Missing", "status": "healthy" if db_path.exists() else "critical"},
        {"label": "Email Status", "value": email_status, "status": email_status.lower().replace(" ", "-")},
        {"label": "Stripe Mode", "value": stripe_mode, "status": "not-configured" if stripe_mode.lower() == "disabled" else "healthy"},
        {"label": "Registration Mode", "value": get_registration_mode(current_app.config["REGISTRATION_MODE"]).title(), "status": "healthy"},
        {"label": "Last Successful Backup", "value": backups[0]["created_at"] if backups else "None", "status": "healthy" if backups else "warning"},
        {"label": "Application Version", "value": str(current_app.config.get("APP_VERSION", app_info.get("application_version", "Unknown"))), "status": "healthy"},
    ]

def validate_content() -> list[dict[str, str]]:
    """Validate content."""
    content_dir = Path(current_app.root_path) / "content"
    results: list[dict[str, str]] = []
    if not content_dir.exists():
        return [{"file": "content/", "status": "error", "message": "Content directory is missing."}]

    json_files = sorted(content_dir.glob("*.json"))
    if not json_files:
        return [{"file": "content/", "status": "warning", "message": "No JSON content files were found."}]

    for path in json_files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, (dict, list)):
                raise ValueError("Top-level JSON value must be an object or array.")
            results.append({"file": path.name, "status": "success", "message": "Valid JSON loaded successfully."})
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            results.append({"file": path.name, "status": "error", "message": str(exc)})
    return results


def system_health() -> list[dict[str, str]]:
    """Handle the system health workflow."""
    checks: list[dict[str, str]] = []
    try:
        get_db().execute("SELECT 1").fetchone()
        checks.append({"name": "Database", "status": "healthy", "detail": "Connected and responding"})
    except sqlite3.Error as exc:
        checks.append({"name": "Database", "status": "error", "detail": str(exc)})

    content_results = validate_content()
    content_errors = sum(1 for item in content_results if item["status"] == "error")
    checks.append({
        "name": "Content Library",
        "status": "healthy" if content_errors == 0 else "error",
        "detail": f"{len(content_results)} file(s) checked; {content_errors} error(s)",
    })

    db_path = Path(current_app.config["DATABASE_PATH"])
    checks.append({
        "name": "Database File",
        "status": "healthy" if db_path.exists() else "error",
        "detail": f"{db_path.stat().st_size / 1024:.1f} KB" if db_path.exists() else "File missing",
    })

    upload_path = Path(current_app.root_path) / "static" / "uploads"
    upload_path.mkdir(parents=True, exist_ok=True)
    checks.append({"name": "Uploads", "status": "healthy", "detail": "Directory available"})
    return checks


def runtime_information() -> dict[str, str]:
    """Handle the runtime information workflow."""
    db_path = Path(current_app.config["DATABASE_PATH"])
    return {
        "Application Version": str(current_app.config.get("APP_VERSION", "Unknown")),
        "Python Version": platform.python_version(),
        "Flask Environment": str(current_app.config.get("ENV", "production")),
        "SQLite Version": sqlite3.sqlite_version,
        "Platform": platform.platform(),
        "Database Path": str(db_path),
        "Database Size": f"{db_path.stat().st_size / 1024:.1f} KB" if db_path.exists() else "Missing",
        "Content Directory": str(Path(current_app.root_path) / "content"),
        "Upload Directory": str(Path(current_app.root_path) / "static" / "uploads"),
        "Python Executable": sys.executable,
        "Checked At": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }



def diagnostic_snapshot() -> dict[str, Any]:
    """Build a support-friendly, installation-wide release diagnostic snapshot."""
    from services.content_packs import get_platform_pack_diagnostics

    db = get_db()
    integrity_row = db.execute("PRAGMA integrity_check").fetchone()
    integrity = integrity_row[0] if integrity_row else "unknown"
    app_info = get_application_info()
    migrations = get_migration_history()
    last_migration = migrations[0] if migrations else None
    existing = {
        row[0]
        for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }

    def count(table: str, where: str = "", params: tuple = ()) -> int:
        if table not in existing:
            return 0
        sql = f"SELECT COUNT(*) FROM {table}"
        if where:
            sql += f" WHERE {where}"
        return int(db.execute(sql, params).fetchone()[0])

    active_cosmetics = {}
    if "family_cosmetics" in existing:
        rows = db.execute(
            """SELECT category, COUNT(*) total
               FROM family_cosmetics
               WHERE active=1
               GROUP BY category"""
        ).fetchall()
        active_cosmetics = {
            row["category"]: row["total"] for row in rows
        }

    return {
        "application_version": str(
            current_app.config.get(
                "APP_VERSION",
                app_info.get("application_version", "Unknown"),
            )
        ),
        "schema_version": app_info.get(
            "schema_version",
            app_info.get("database_version", "Unknown"),
        ),
        "achievement_engine_version": "2",
        "database_integrity": integrity,
        "last_migration": dict(last_migration) if last_migration else None,
        "active_family_count": count("families", "status='active'"),
        "counts": {
            "Active Families": count("families", "status='active'"),
            "Children": count("users", "role='child'"),
            "Active Quests": count("chores", "active=1"),
            "Active Adventures": count("adventures_v2", "active=1"),
            "Active Rewards": count("rewards", "active=1"),
            "Assignments": count("assignments"),
            "Achievement Unlocks": count("user_achievements"),
        },
        "active_cosmetics": active_cosmetics,
        "packs": get_platform_pack_diagnostics(),
    }


def _table_exists(db, name: str) -> bool:
    return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def _table_columns(db, name: str) -> set[str]:
    if not _table_exists(db, name):
        return set()
    return {row["name"] for row in db.execute(f"PRAGMA table_info({name})").fetchall()}


def list_platform_families(search: str = "", status: str = "all", subscription: str = "all", sort: str = "newest"):
    """Return customer families for the Application Owner management list."""
    db = get_db()
    search = (search or "").strip()
    where = ["1=1"]
    params: list[Any] = []
    if status and status != "all":
        where.append("f.status=?")
        params.append(status)
    if search:
        like = f"%{search}%"
        where.append("(f.name LIKE ? OR au.display_name LIKE ? OR au.email LIKE ?)")
        params.extend([like, like, like])
    if subscription and subscription != "all":
        where.append("COALESCE(fs.status,'none')=?")
        params.append(subscription)
    order_map = {
        "name": "f.name COLLATE NOCASE ASC",
        "oldest": "f.created_at ASC, f.id ASC",
        "last_active": "COALESCE(MAX(au.last_login_at), f.updated_at, f.created_at) DESC",
        "newest": "f.created_at DESC, f.id DESC",
    }
    order_by = order_map.get(sort, order_map["newest"])
    sql = f"""
        SELECT f.id,f.name,f.status,f.created_at,f.updated_at,
               MAX(CASE WHEN fm.role='owner' THEN au.display_name END) AS primary_parent,
               MAX(CASE WHEN fm.role='owner' THEN au.email END) AS primary_email,
               COUNT(DISTINCT CASE WHEN u.role='child' AND u.active=1 THEN u.id END) AS child_count,
               COALESCE(fs.status,'none') AS subscription_status,
               MAX(au.last_login_at) AS last_activity
        FROM families f
        LEFT JOIN family_memberships fm ON fm.family_id=f.id AND fm.active=1
        LEFT JOIN account_users au ON au.id=fm.account_user_id
        LEFT JOIN users u ON u.family_id=f.id
        LEFT JOIN family_subscriptions fs ON fs.id=(SELECT fs2.id FROM family_subscriptions fs2 WHERE fs2.family_id=f.id ORDER BY fs2.updated_at DESC,fs2.id DESC LIMIT 1)
        WHERE {' AND '.join(where)}
        GROUP BY f.id
        ORDER BY {order_by}
    """
    return db.execute(sql, params).fetchall()


def get_platform_family_detail(family_id: int):
    """Return a complete read-only support view for one family."""
    db = get_db()
    family = db.execute("SELECT * FROM families WHERE id=?", (family_id,)).fetchone()
    if family is None:
        return None
    parents = db.execute(
        """SELECT au.id,au.display_name,au.email,au.active,au.email_verified,au.last_login_at,
                  fm.role,fm.active AS membership_active,fm.created_at
           FROM family_memberships fm JOIN account_users au ON au.id=fm.account_user_id
           WHERE fm.family_id=? ORDER BY CASE fm.role WHEN 'owner' THEN 0 WHEN 'parent' THEN 1 ELSE 2 END, au.display_name""",
        (family_id,),
    ).fetchall()
    children = db.execute(
        """SELECT id,name,initial,total_xp,total_points,current_level,current_streak,active,avatar_key,created_at
           FROM users WHERE family_id=? AND role='child' ORDER BY active DESC,name""",
        (family_id,),
    ).fetchall()
    subscription = db.execute(
        "SELECT * FROM family_subscriptions WHERE family_id=? ORDER BY updated_at DESC,id DESC LIMIT 1",
        (family_id,),
    ).fetchone() if _table_exists(db, "family_subscriptions") else None

    def scalar(sql: str, params: tuple = ()) -> int:
        try:
            row = db.execute(sql, params).fetchone()
            return int(row[0] or 0) if row else 0
        except sqlite3.Error:
            return 0

    stats = {
        "Quests Completed": scalar("SELECT COUNT(*) FROM assignments WHERE family_id=? AND status='approved'", (family_id,)) if "family_id" in _table_columns(db,"assignments") else scalar("SELECT COUNT(*) FROM assignments a JOIN users u ON u.id=a.user_id WHERE u.family_id=? AND a.status='approved'", (family_id,)),
        "Adventures Completed": scalar(
            "SELECT COUNT(*) FROM adventure_instances_v2 WHERE family_id=? AND status='completed' AND completed_at IS NOT NULL",
            (family_id,),
        ) if _table_exists(db, "adventure_instances_v2") else 0,
        "Rewards Redeemed": scalar("SELECT COUNT(*) FROM reward_requests WHERE family_id=? AND status='approved'", (family_id,)) if "family_id" in _table_columns(db,"reward_requests") else 0,
        "Current XP": scalar("SELECT COALESCE(SUM(total_xp),0) FROM users WHERE family_id=? AND role='child' AND active=1", (family_id,)),
        "Stars Earned": scalar("SELECT COALESCE(SUM(total_points),0) FROM users WHERE family_id=? AND role='child' AND active=1", (family_id,)),
        "Longest Streak": scalar("SELECT COALESCE(MAX(current_streak),0) FROM users WHERE family_id=? AND role='child'", (family_id,)),
    }
    activity = db.execute(
        "SELECT * FROM audit_log WHERE family_id=? ORDER BY created_at DESC,id DESC LIMIT 40", (family_id,)
    ).fetchall() if _table_exists(db,"audit_log") else []
    installed_packs = []
    # MGMT-0007: family_content_packs is the canonical installation table.
    # Join the catalog when available so Manage Families can show useful pack
    # metadata while remaining strictly scoped to the selected family.
    if _table_exists(db, "family_content_packs"):
        if _table_exists(db, "content_packs"):
            installed_packs = db.execute(
                """SELECT fcp.pack_key,
                          COALESCE(cp.name, fcp.pack_key) AS name,
                          fcp.installed_version,
                          fcp.status,
                          fcp.installed_at,
                          fcp.updated_at
                   FROM family_content_packs fcp
                   LEFT JOIN content_packs cp ON cp.pack_key=fcp.pack_key
                   WHERE fcp.family_id=?
                   ORDER BY CASE fcp.status WHEN 'active' THEN 0 ELSE 1 END,
                            COALESCE(cp.name, fcp.pack_key) COLLATE NOCASE""",
                (family_id,),
            ).fetchall()
        else:
            installed_packs = db.execute(
                """SELECT pack_key, pack_key AS name, installed_version,
                          status, installed_at, updated_at
                   FROM family_content_packs
                   WHERE family_id=?
                   ORDER BY CASE status WHEN 'active' THEN 0 ELSE 1 END,
                            pack_key COLLATE NOCASE""",
                (family_id,),
            ).fetchall()
    return {"family": family, "parents": parents, "children": children, "subscription": subscription,
            "statistics": stats, "activity": activity, "installed_packs": installed_packs}


def perform_family_admin_action(family_id: int, action: str, actor_name: str) -> str:
    """Perform an audited, installation-owner family lifecycle action."""
    db = get_db()
    family = db.execute("SELECT id,name,status FROM families WHERE id=?", (family_id,)).fetchone()
    if family is None:
        raise LookupError("Family not found")
    labels = {"suspend": "suspended", "reactivate": "active", "archive": "archived"}
    if action in labels:
        db.execute("UPDATE families SET status=?,updated_at=CURRENT_TIMESTAMP WHERE id=?", (labels[action], family_id))
        if action in {"suspend", "archive"}:
            db.execute("UPDATE account_users SET auth_version=auth_version+1,updated_at=CURRENT_TIMESTAMP WHERE id IN (SELECT account_user_id FROM family_memberships WHERE family_id=?)", (family_id,))
        detail = f"{action.title()} family {family['name']}"
    elif action == "force_logout":
        db.execute("UPDATE account_users SET auth_version=auth_version+1,updated_at=CURRENT_TIMESTAMP WHERE id IN (SELECT account_user_id FROM family_memberships WHERE family_id=?)", (family_id,))
        detail = f"Forced logout for all accounts in {family['name']}"
    else:
        raise ValueError("Unsupported family action")
    db.commit()
    log_audit(action=f"family_{action}", entity_type="family", entity_id=family_id, details=detail,
              actor_type="application_owner", actor_name=actor_name)
    return detail



def platform_subscription_management(
    search: str = "",
    status: str = "all",
    sort: str = "attention",
) -> dict[str, object]:
    """Return installation-wide subscription metrics and family billing rows."""
    from services.billing import ensure_billing_schema

    ensure_billing_schema()
    db = get_db()

    normalized_status = (status or "all").strip().lower()
    allowed_statuses = {
        "all", "active", "trialing", "past_due", "canceled", "cancelled",
        "incomplete", "unpaid", "none",
    }
    if normalized_status not in allowed_statuses:
        normalized_status = "all"

    search = (search or "").strip()
    where = ["1=1"]
    params: list[object] = []

    if search:
        like = f"%{search}%"
        where.append(
            """(
                f.name LIKE ? COLLATE NOCASE
                OR COALESCE(fs.customer_email,'') LIKE ? COLLATE NOCASE
                OR COALESCE(fs.stripe_customer_id,'') LIKE ? COLLATE NOCASE
                OR COALESCE(fs.stripe_subscription_id,'') LIKE ? COLLATE NOCASE
            )"""
        )
        params.extend([like, like, like, like])

    if normalized_status == "none":
        where.append("fs.id IS NULL")
    elif normalized_status != "all":
        if normalized_status == "cancelled":
            normalized_status = "canceled"
        where.append("fs.status=?")
        params.append(normalized_status)

    order_map = {
        "family": "f.name COLLATE NOCASE ASC",
        "newest": "COALESCE(fs.updated_at,f.created_at) DESC, f.id DESC",
        "status": "COALESCE(fs.status,'none') ASC, f.name COLLATE NOCASE ASC",
        "attention": """CASE COALESCE(fs.status,'none')
                         WHEN 'past_due' THEN 0
                         WHEN 'unpaid' THEN 1
                         WHEN 'incomplete' THEN 2
                         WHEN 'trialing' THEN 3
                         WHEN 'active' THEN 4
                         WHEN 'canceled' THEN 5
                         ELSE 6 END,
                       COALESCE(fs.updated_at,f.created_at) DESC""",
    }
    selected_sort = sort if sort in order_map else "attention"

    rows = db.execute(
        f"""SELECT f.id AS family_id,
                   f.name AS family_name,
                   f.status AS family_status,
                   fs.id AS subscription_id,
                   COALESCE(fs.status,'none') AS subscription_status,
                   fs.customer_email,
                   fs.stripe_customer_id,
                   fs.stripe_subscription_id,
                   fs.current_period_end,
                   COALESCE(fs.cancel_at_period_end,0) AS cancel_at_period_end,
                   fs.cancel_at,
                   fs.grace_until,
                   fs.created_at AS subscription_created_at,
                   fs.updated_at AS subscription_updated_at
            FROM families f
            LEFT JOIN family_subscriptions fs ON fs.family_id=f.id
            WHERE {' AND '.join(where)}
            ORDER BY {order_map[selected_sort]}""",
        params,
    ).fetchall()

    metrics = {
        "Total Families": db.execute("SELECT COUNT(*) FROM families").fetchone()[0],
        "Active": db.execute(
            "SELECT COUNT(*) FROM family_subscriptions WHERE status='active'"
        ).fetchone()[0],
        "Trialing": db.execute(
            "SELECT COUNT(*) FROM family_subscriptions WHERE status='trialing'"
        ).fetchone()[0],
        "Needs Attention": db.execute(
            """SELECT COUNT(*) FROM family_subscriptions
               WHERE status IN ('past_due','unpaid','incomplete')"""
        ).fetchone()[0],
        "No Subscription": db.execute(
            """SELECT COUNT(*) FROM families f
               LEFT JOIN family_subscriptions fs ON fs.family_id=f.id
               WHERE fs.id IS NULL"""
        ).fetchone()[0],
        "Scheduled Cancellation": db.execute(
            "SELECT COUNT(*) FROM family_subscriptions WHERE cancel_at_period_end=1"
        ).fetchone()[0],
    }

    return {
        "subscriptions": rows,
        "metrics": metrics,
        "search": search,
        "selected_status": normalized_status,
        "selected_sort": selected_sort,
    }


def list_platform_parent_accounts(search: str = "", status: str = "all", role: str = "all", email_status: str = "all", sort: str = "name"):
    """Return parent accounts and pending invitations for owner support."""
    db = get_db()
    search = (search or "").strip()
    where = ["COALESCE(au.platform_role,'none')='none'", "fm.role IN ('owner','parent')"]
    params: list[Any] = []
    if search:
        like = f"%{search}%"
        where.append("(au.display_name LIKE ? OR au.email LIKE ? OR f.name LIKE ?)")
        params.extend([like, like, like])
    if role in {"owner", "parent"}:
        where.append("fm.role=?")
        params.append(role)
    if email_status == "verified":
        where.append("au.email_verified=1")
    elif email_status == "unverified":
        where.append("au.email_verified=0")
    if status == "active":
        where.append("au.active=1 AND fm.active=1")
    elif status == "disabled":
        where.append("(au.active=0 OR fm.active=0)")

    order_map = {
        "name": "au.display_name COLLATE NOCASE ASC",
        "email": "au.email COLLATE NOCASE ASC",
        "last_login": "au.last_login_at DESC, au.display_name COLLATE NOCASE ASC",
        "created": "au.created_at DESC, au.id DESC",
    }
    sql = f"""
        SELECT au.id, au.display_name, au.email, au.email_verified, au.active,
               au.last_login_at, au.created_at, au.updated_at, fm.role,
               fm.active AS membership_active, f.id AS family_id, f.name AS family_name,
               'account' AS record_type
        FROM account_users au
        JOIN family_memberships fm ON fm.account_user_id=au.id
        JOIN families f ON f.id=fm.family_id
        WHERE {' AND '.join(where)}
        ORDER BY {order_map.get(sort, order_map['name'])}
    """
    results = [dict(row) for row in db.execute(sql, params).fetchall()]

    if status in {"all", "pending"} and _table_exists(db, "parent_invitations"):
        invite_where = ["pi.status='pending'"]
        invite_params: list[Any] = []
        if search:
            like = f"%{search}%"
            invite_where.append("(pi.email LIKE ? OR f.name LIKE ?)")
            invite_params.extend([like, like])
        if role in {"owner", "parent"}:
            # Invitations are always additional parents in the current workflow.
            if role == "owner":
                invite_where.append("1=0")
        invitations = db.execute(
            f"""SELECT pi.id, '' AS display_name, pi.email, 0 AS email_verified, 0 AS active,
                       NULL AS last_login_at, pi.created_at, pi.created_at AS updated_at,
                       pi.role, 0 AS membership_active, f.id AS family_id, f.name AS family_name,
                       'invitation' AS record_type
                FROM parent_invitations pi JOIN families f ON f.id=pi.family_id
                WHERE {' AND '.join(invite_where)} ORDER BY pi.created_at DESC""",
            invite_params,
        ).fetchall()
        results.extend(dict(row) for row in invitations)
    return results


def get_platform_parent_account_detail(account_id: int):
    """Return read-only support information for one parent account."""
    db = get_db()
    account = db.execute(
        """SELECT au.id,au.display_name,au.email,au.email_verified,au.active,
                  au.last_login_at,au.created_at,au.updated_at,au.auth_version,
                  fm.role,fm.active AS membership_active,f.id AS family_id,f.name AS family_name,
                  f.status AS family_status
           FROM account_users au
           JOIN family_memberships fm ON fm.account_user_id=au.id
           JOIN families f ON f.id=fm.family_id
           WHERE au.id=? AND COALESCE(au.platform_role,'none')='none'
           ORDER BY fm.active DESC,fm.id LIMIT 1""",
        (account_id,),
    ).fetchone()
    if account is None:
        return None
    audit = db.execute(
        """SELECT * FROM audit_log
           WHERE entity_type='parent_account' AND entity_id=?
           ORDER BY created_at DESC,id DESC LIMIT 40""",
        (account_id,),
    ).fetchall() if _table_exists(db, "audit_log") else []
    return {"parent_account": account, "account_audit": audit}


def perform_parent_account_admin_action(account_id: int, action: str, actor_name: str) -> str:
    """Perform an audited parent-account support action without exposing credentials."""
    db = get_db()
    account = db.execute(
        """SELECT au.id,au.display_name,au.email,au.active,fm.family_id
           FROM account_users au JOIN family_memberships fm ON fm.account_user_id=au.id
           WHERE au.id=? AND COALESCE(au.platform_role,'none')='none' LIMIT 1""",
        (account_id,),
    ).fetchone()
    if account is None:
        raise LookupError("Parent account not found")

    if action == "disable":
        db.execute("UPDATE account_users SET active=0,auth_version=auth_version+1,updated_at=CURRENT_TIMESTAMP WHERE id=?", (account_id,))
        detail = f"Disabled parent account {account['email']}"
    elif action == "reactivate":
        db.execute("UPDATE account_users SET active=1,updated_at=CURRENT_TIMESTAMP WHERE id=?", (account_id,))
        detail = f"Reactivated parent account {account['email']}"
    elif action == "verify_email":
        db.execute("UPDATE account_users SET email_verified=1,updated_at=CURRENT_TIMESTAMP WHERE id=?", (account_id,))
        detail = f"Administratively verified email for {account['email']}"
    elif action == "force_logout":
        db.execute("UPDATE account_users SET auth_version=auth_version+1,updated_at=CURRENT_TIMESTAMP WHERE id=?", (account_id,))
        detail = f"Forced logout for {account['email']}"
    elif action == "unlock":
        # Login throttling is IP+email based. Clear login throttles so the parent can retry.
        if _table_exists(db, "security_rate_limits"):
            db.execute("DELETE FROM security_rate_limits WHERE action='account_login'")
        detail = f"Cleared account login throttles for support request involving {account['email']}"
    else:
        raise ValueError("Unsupported parent account action")
    db.commit()
    log_audit(action=f"parent_account_{action}", entity_type="parent_account", entity_id=account_id,
              details=detail, actor_type="application_owner", actor_name=actor_name)
    return detail

# Phase 2 Sprint 2D - read-only platform reporting helpers.
def _report_table_names() -> set[str]:
    return {row[0] for row in get_db().execute("SELECT name FROM sqlite_master WHERE type='table'")}


def _report_scalar(sql: str, params: tuple = ()) -> int:
    try:
        row = get_db().execute(sql, params).fetchone()
        return int(row[0] or 0) if row else 0
    except sqlite3.Error:
        return 0


def platform_report(report_key: str, start_date: str | None = None, end_date: str | None = None) -> dict[str, Any]:
    """Return one read-only platform report with summary metrics and exportable rows."""
    tables = _report_table_names()
    start = start_date or "1900-01-01"
    end = end_date or "2999-12-31"
    end_exclusive = f"{end} 23:59:59"
    key = report_key.strip().lower()
    title_map = {
        "family-growth": "Family Growth", "user-activity": "User Activity",
        "quest-adventure": "Quest & Adventure Usage", "reward-usage": "Reward Usage",
        "subscriptions": "Subscription Status", "pack-adoption": "Pack Adoption",
        "security-events": "Security Events", "application-errors": "Application Errors",
    }
    if key not in title_map:
        raise LookupError("Unknown platform report.")
    metrics: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    columns: list[str] = []

    if key == "family-growth":
        total = _report_scalar("SELECT COUNT(*) FROM families") if "families" in tables else 0
        active = _report_scalar("SELECT COUNT(*) FROM families WHERE status='active'") if "families" in tables else 0
        suspended = _report_scalar("SELECT COUNT(*) FROM families WHERE status='suspended'") if "families" in tables else 0
        archived = _report_scalar("SELECT COUNT(*) FROM families WHERE status='archived'") if "families" in tables else 0
        new_period = _report_scalar("SELECT COUNT(*) FROM families WHERE created_at BETWEEN ? AND ?", (start, end_exclusive)) if "families" in tables else 0
        metrics = [{"label":"Total Families","value":total},{"label":"New in Period","value":new_period},{"label":"Active","value":active},{"label":"Suspended","value":suspended},{"label":"Archived","value":archived},{"label":"Paid Families","value":"—"}]
        if "families" in tables:
            rows = [dict(r) for r in get_db().execute("SELECT id, name, status, created_at FROM families WHERE created_at BETWEEN ? AND ? ORDER BY created_at DESC", (start, end_exclusive)).fetchall()]
        columns = ["id","name","status","created_at"]
    elif key == "user-activity":
        parents = _report_scalar("SELECT COUNT(DISTINCT account_user_id) FROM family_memberships WHERE active=1", ()) if "family_memberships" in tables else 0
        children = _report_scalar("SELECT COUNT(*) FROM users WHERE role='child' AND active=1") if "users" in tables else 0
        recent_logins = _report_scalar("SELECT COUNT(*) FROM account_users WHERE last_login_at BETWEEN ? AND ?", (start, end_exclusive)) if "account_users" in tables else 0
        families = _report_scalar("SELECT COUNT(*) FROM families") if "families" in tables else 0
        avg = round(children / families, 1) if families else 0
        metrics = [{"label":"Parent Accounts","value":parents},{"label":"Active Children","value":children},{"label":"Recent Logins","value":recent_logins},{"label":"Average Children / Family","value":avg}]
        if {"account_users","family_memberships","families"}.issubset(tables):
            rows = [dict(r) for r in get_db().execute("""SELECT au.display_name, au.email, f.name AS family, fm.role, au.last_login_at
                FROM family_memberships fm JOIN account_users au ON au.id=fm.account_user_id JOIN families f ON f.id=fm.family_id
                WHERE fm.active=1 ORDER BY COALESCE(au.last_login_at,'') DESC""").fetchall()]
        columns = ["display_name","email","family","role","last_login_at"]
    elif key == "quest-adventure":
        quests = _report_scalar("SELECT COUNT(*) FROM assignments WHERE status='approved' AND approved_at BETWEEN ? AND ?", (start, end_exclusive)) if "assignments" in tables else 0
        adventures = _report_scalar("SELECT COUNT(*) FROM adventure_instances_v2 WHERE status='completed' AND completed_at BETWEEN ? AND ?", (start, end_exclusive)) if "adventure_instances_v2" in tables else 0
        xp = _report_scalar("SELECT COALESCE(SUM(xp),0) FROM xp_history WHERE created_at BETWEEN ? AND ?", (start, end_exclusive)) if "xp_history" in tables else 0
        stars = _report_scalar("SELECT COALESCE(SUM(CASE WHEN amount>0 THEN amount ELSE 0 END),0) FROM star_transactions WHERE created_at BETWEEN ? AND ?", (start, end_exclusive)) if "star_transactions" in tables else 0
        metrics = [{"label":"Approved Quests","value":quests},{"label":"Completed Adventures","value":adventures},{"label":"XP Awarded","value":xp},{"label":"Stars Earned","value":stars}]
        rows = [{"activity":"Approved Quests","count":quests},{"activity":"Completed Adventures","count":adventures},{"activity":"XP Awarded","count":xp},{"activity":"Stars Earned","count":stars}]
        columns = ["activity","count"]
    elif key == "reward-usage":
        req = _report_scalar("SELECT COUNT(*) FROM reward_requests WHERE requested_at BETWEEN ? AND ?", (start, end_exclusive)) if "reward_requests" in tables else 0
        approved = _report_scalar("SELECT COUNT(*) FROM reward_requests WHERE status IN ('approved','redeemed') AND approved_at BETWEEN ? AND ?", (start, end_exclusive)) if "reward_requests" in tables else 0
        denied = _report_scalar("SELECT COUNT(*) FROM reward_requests WHERE status='denied' AND denied_at BETWEEN ? AND ?", (start, end_exclusive)) if "reward_requests" in tables else 0
        spent = abs(_report_scalar("SELECT COALESCE(SUM(amount),0) FROM star_transactions WHERE amount<0 AND created_at BETWEEN ? AND ?", (start, end_exclusive))) if "star_transactions" in tables else 0
        metrics = [{"label":"Reward Requests","value":req},{"label":"Approved","value":approved},{"label":"Denied","value":denied},{"label":"Stars Redeemed","value":spent}]
        if {"reward_requests","rewards","users"}.issubset(tables):
            rows = [dict(r) for r in get_db().execute("""SELECT rr.id, r.name AS reward, u.name AS child, rr.status, rr.requested_at
                FROM reward_requests rr JOIN rewards r ON r.id=rr.reward_id JOIN users u ON u.id=rr.child_id
                WHERE rr.requested_at BETWEEN ? AND ? ORDER BY rr.requested_at DESC""", (start,end_exclusive)).fetchall()]
        columns = ["id","reward","child","status","requested_at"]
    elif key == "subscriptions":
        statuses = ["trialing","active","past_due","suspended","cancelled"]
        metrics = [{"label":s.replace('_',' ').title(),"value":_report_scalar("SELECT COUNT(*) FROM family_subscriptions WHERE status=?",(s,)) if "family_subscriptions" in tables else 0} for s in statuses]
        if {"family_subscriptions","families"}.issubset(tables):
            rows=[dict(r) for r in get_db().execute("SELECT f.name AS family, fs.status, fs.current_period_end, fs.updated_at FROM family_subscriptions fs JOIN families f ON f.id=fs.family_id ORDER BY fs.updated_at DESC").fetchall()]
        columns=["family","status","current_period_end","updated_at"]
    elif key == "pack-adoption":
        installed = _report_scalar("SELECT COUNT(*) FROM family_content_packs WHERE status='installed'") if "family_content_packs" in tables else 0
        families_using = _report_scalar("SELECT COUNT(DISTINCT family_id) FROM family_content_packs WHERE status='installed'") if "family_content_packs" in tables else 0
        metrics=[{"label":"Installed Packs","value":installed},{"label":"Families Using Packs","value":families_using},{"label":"Paid Packs","value":"—"},{"label":"Updates Available","value":"—"}]
        if {"family_content_packs","families"}.issubset(tables):
            rows=[dict(r) for r in get_db().execute("SELECT f.name AS family, fp.pack_key, fp.installed_version, fp.status, fp.installed_at FROM family_content_packs fp JOIN families f ON f.id=fp.family_id ORDER BY fp.installed_at DESC").fetchall()]
        columns=["family","pack_key","installed_version","status","installed_at"]
    elif key == "security-events":
        failed = _report_scalar("SELECT COALESCE(SUM(attempt_count),0) FROM security_rate_limits WHERE updated_at BETWEEN ? AND ?",(start,end_exclusive)) if "security_rate_limits" in tables else 0
        resets = _report_scalar("SELECT COUNT(*) FROM password_reset_tokens WHERE created_at BETWEEN ? AND ?",(start,end_exclusive)) if "password_reset_tokens" in tables else 0
        admin = _report_scalar("SELECT COUNT(*) FROM audit_log WHERE created_at BETWEEN ? AND ?",(start,end_exclusive)) if "audit_log" in tables else 0
        metrics=[{"label":"Failed Login Attempts","value":failed},{"label":"Password Resets","value":resets},{"label":"Administrative Actions","value":admin},{"label":"Locked Accounts","value":"—"}]
        if "audit_log" in tables:
            rows=[dict(r) for r in get_db().execute("SELECT action, actor_name, entity_type, details, created_at FROM audit_log WHERE created_at BETWEEN ? AND ? ORDER BY created_at DESC LIMIT 500",(start,end_exclusive)).fetchall()]
        columns=["action","actor_name","entity_type","details","created_at"]
    else:
        unresolved = _report_scalar("SELECT COUNT(*) FROM error_log WHERE COALESCE(resolved,0)=0") if "error_log" in tables else 0
        recent = _report_scalar("SELECT COUNT(*) FROM error_log WHERE created_at BETWEEN ? AND ?",(start,end_exclusive)) if "error_log" in tables else 0
        metrics=[{"label":"Unresolved Errors","value":unresolved},{"label":"Errors in Period","value":recent},{"label":"Backup Failures","value":"—"},{"label":"Stripe / Webhook Failures","value":"—"}]
        if "error_log" in tables:
            rows=[dict(r) for r in get_db().execute("SELECT error_type, message, request_path, resolved, created_at FROM error_log WHERE created_at BETWEEN ? AND ? ORDER BY created_at DESC LIMIT 500",(start,end_exclusive)).fetchall()]
        columns=["error_type","message","request_path","resolved","created_at"]

    return {"key":key,"title":title_map[key],"metrics":metrics,"rows":rows,"columns":columns,"start_date":start_date or "","end_date":end_date or ""}


def platform_reports_dashboard() -> list[dict[str, Any]]:
    """Return report-card metadata and current headline values."""
    cards=[]
    definitions=[
      ("family-growth","📈","Family Growth","Registrations and family status"),
      ("user-activity","👥","User Activity","Parent, child, and login activity"),
      ("quest-adventure","🗡️","Quest & Adventure Usage","Approved accomplishments and awards"),
      ("reward-usage","🎁","Reward Usage","Requests, approvals, and redemptions"),
      ("subscriptions","💳","Subscription Status","Trials and account billing states"),
      ("pack-adoption","📦","Pack Adoption","Installed content across families"),
      ("security-events","🔒","Security Events","Authentication and owner actions"),
      ("application-errors","⚠️","Application Errors","Errors and operational warnings"),
    ]
    for key,icon,title,description in definitions:
        report=platform_report(key)
        headline=report["metrics"][0]["value"] if report["metrics"] else 0
        cards.append({"key":key,"icon":icon,"title":title,"description":description,"headline":headline})
    return cards
