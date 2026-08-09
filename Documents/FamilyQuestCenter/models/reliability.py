"""Family Quest Center developer documentation.

File: models/reliability.py
Purpose: Provides database access and domain operations for reliability data.

Maintenance notes:
- Preserve tenant and family data isolation when changing queries.
- Keep route, template, and schema changes synchronized.
- Run regression tests before release packaging.
Documentation updated: 2026-07-31.
"""

from __future__ import annotations

import csv
import io
import json
import sqlite3
import zipfile
from datetime import datetime
from pathlib import Path

from flask import current_app

from database import get_db
from services.tenant_context import get_current_family_id


def backup_directory() -> Path:
    """Handle the backup directory workflow."""
    path = Path(current_app.config.get("BACKUP_DIRECTORY", Path(current_app.root_path) / "backups"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def _safe_backup_name(name: str) -> str:
    """Handle the safe backup name workflow."""
    candidate = Path(name).name
    if candidate != name or not candidate.endswith(".db"):
        raise ValueError("Invalid backup name.")
    return candidate


def create_database_backup() -> Path:
    """Create database backup."""
    source = Path(current_app.config["DATABASE_PATH"])
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    target = backup_directory() / f"family_quest_center_{timestamp}.db"

    source_db = sqlite3.connect(source)
    try:
        target_db = sqlite3.connect(target)
        try:
            source_db.backup(target_db)
        finally:
            target_db.close()
    finally:
        source_db.close()

    check = sqlite3.connect(target)
    try:
        result = check.execute("PRAGMA integrity_check").fetchone()[0]
        if result != "ok":
            target.unlink(missing_ok=True)
            raise RuntimeError(f"Backup integrity check failed: {result}")
    finally:
        check.close()
    return target


def list_backups() -> list[dict[str, object]]:
    """Handle the list backups workflow."""
    items = []
    for path in sorted(backup_directory().glob("*.db"), reverse=True):
        stat = path.stat()
        items.append({
            "name": path.name,
            "size_bytes": stat.st_size,
            "size_text": f"{stat.st_size / 1024:.1f} KB",
            "created_at": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
        })
    return items


def get_backup_path(name: str) -> Path:
    """Retrieve backup path."""
    path = backup_directory() / _safe_backup_name(name)
    if not path.exists():
        raise FileNotFoundError("Backup not found.")
    return path


def delete_backup(name: str) -> None:
    """Delete backup."""
    get_backup_path(name).unlink()


def _copy_sqlite_database(source_path: Path, target_path: Path) -> None:
    """Copy one SQLite database into another using SQLite's backup API.

    This avoids replacing the live database file, which Windows blocks while
    any process has the file open. Both connections are always closed before
    returning so the application can reopen the restored database normally.
    """
    source_db = sqlite3.connect(source_path)
    try:
        target_db = sqlite3.connect(target_path, timeout=10)
        try:
            target_db.execute("PRAGMA busy_timeout = 10000")
            source_db.backup(target_db)
            target_db.commit()
        finally:
            target_db.close()
    finally:
        source_db.close()


def restore_backup(name: str) -> Path:
    """Restore a validated backup and return the automatic safety backup."""
    backup = get_backup_path(name)
    check = sqlite3.connect(backup)
    try:
        result = check.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        check.close()
    if result != "ok":
        raise RuntimeError(f"Backup integrity check failed: {result}")

    database_path = Path(current_app.config["DATABASE_PATH"])
    safety_copy = create_database_backup()

    # Remove debris left by older file-replacement restore versions. The new
    # restore method does not create or rename a .restore.tmp file.
    database_path.with_suffix(".restore.tmp").unlink(missing_ok=True)

    try:
        _copy_sqlite_database(backup, database_path)

        restored_db = sqlite3.connect(database_path)
        try:
            restored_result = restored_db.execute("PRAGMA integrity_check").fetchone()[0]
        finally:
            restored_db.close()
        if restored_result != "ok":
            raise RuntimeError(f"Restored database integrity check failed: {restored_result}")
    except Exception:
        # Best-effort rollback to the automatically created pre-restore copy.
        _copy_sqlite_database(safety_copy, database_path)
        raise

    return safety_copy


def _table_exists(table: str) -> bool:
    """Handle the table exists workflow."""
    return get_db().execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def build_export_zip() -> io.BytesIO:
    """Build an export containing only the active family's tenant-owned data."""
    db = get_db()
    family_id = get_current_family_id()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Most tenant tables now carry family_id directly. Shared achievement
    # definitions are included as read-only reference data; chain steps are
    # scoped through their family-owned parent chain.
    export_queries = {
        "users": ("SELECT * FROM users WHERE family_id=?", (family_id,)),
        "chores": ("SELECT * FROM chores WHERE family_id=?", (family_id,)),
        "quest_schedules": ("SELECT * FROM quest_schedules WHERE family_id=?", (family_id,)),
        "assignments": ("SELECT * FROM assignments WHERE family_id=?", (family_id,)),
        "xp_history": ("SELECT * FROM xp_history WHERE family_id=?", (family_id,)),
        "star_transactions": ("SELECT * FROM star_transactions WHERE family_id=?", (family_id,)),
        "rewards": ("SELECT * FROM rewards WHERE family_id=?", (family_id,)),
        "reward_requests": ("SELECT * FROM reward_requests WHERE family_id=?", (family_id,)),
        "reward_history": ("SELECT * FROM reward_history WHERE family_id=?", (family_id,)),
        "achievements": ("SELECT * FROM achievements WHERE active=1", ()),
        "user_achievements": ("SELECT * FROM user_achievements WHERE family_id=?", (family_id,)),
        "quest_chains": ("SELECT * FROM quest_chains WHERE family_id=?", (family_id,)),
        "quest_chain_steps": (
            "SELECT qcs.* FROM quest_chain_steps qcs "
            "JOIN quest_chains qc ON qc.id=qcs.chain_id WHERE qc.family_id=?",
            (family_id,),
        ),
        "quest_chain_instances": ("SELECT * FROM quest_chain_instances WHERE family_id=?", (family_id,)),
        "family_challenges": ("SELECT * FROM family_challenges WHERE family_id=?", (family_id,)),
        "audit_log": ("SELECT * FROM audit_log WHERE family_id=?", (family_id,)),
    }

    memory = io.BytesIO()
    manifest = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "family_id": family_id,
        "scope": "active_family_only",
        "tables": [],
    }
    with zipfile.ZipFile(memory, "w", zipfile.ZIP_DEFLATED) as archive:
        for table, (sql, params) in export_queries.items():
            if not _table_exists(table):
                continue
            rows = db.execute(sql, params).fetchall()
            output = io.StringIO(newline="")
            if rows:
                writer = csv.DictWriter(output, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(dict(row) for row in rows)
            archive.writestr(f"{table}.csv", output.getvalue())
            manifest["tables"].append({"name": table, "rows": len(rows)})
        archive.writestr("manifest.json", json.dumps(manifest, indent=2))
    memory.seek(0)
    memory.download_name = f"family_quest_export_{timestamp}.zip"  # type: ignore[attr-defined]
    return memory


def integrity_report() -> dict[str, object]:
    """Return a user-friendly, grouped System Health report."""
    db = get_db()
    checked_at = datetime.now()

    def item(name: str, status: str, detail: str, *, action_url: str | None = None,
             action_text: str | None = None) -> dict[str, str | None]:
        return {
            "name": name,
            "status": status,
            "detail": detail,
            "action_url": action_url,
            "action_text": action_text,
        }

    groups: list[dict[str, object]] = []

    database_checks: list[dict[str, str | None]] = []
    sqlite_result = db.execute("PRAGMA integrity_check").fetchone()[0]
    database_checks.append(item(
        "SQLite Database",
        "pass" if sqlite_result == "ok" else "fail",
        "Healthy" if sqlite_result == "ok" else str(sqlite_result),
    ))

    foreign_keys = db.execute("PRAGMA foreign_key_check").fetchall()
    database_checks.append(item(
        "Foreign-Key References",
        "pass" if not foreign_keys else "fail",
        "No violations" if not foreign_keys else f"{len(foreign_keys)} violation(s)",
    ))

    custom_checks = [
        ("Assignments Have Children", "SELECT COUNT(*) FROM assignments a LEFT JOIN users u ON u.id=a.child_id WHERE u.id IS NULL"),
        ("Assignments Have Quests", "SELECT COUNT(*) FROM assignments a LEFT JOIN chores c ON c.id=a.chore_id WHERE c.id IS NULL"),
        ("XP History Has Children", "SELECT COUNT(*) FROM xp_history x LEFT JOIN users u ON u.id=x.child_id WHERE u.id IS NULL"),
        ("Star Ledger Has Children", "SELECT COUNT(*) FROM star_transactions s LEFT JOIN users u ON u.id=s.user_id WHERE u.id IS NULL"),
        ("Child Star Balances", "SELECT COUNT(*) FROM (SELECT u.id, COALESCE(SUM(s.amount),0) balance FROM users u LEFT JOIN star_transactions s ON s.user_id=u.id WHERE u.role='child' GROUP BY u.id HAVING balance < 0)"),
    ]
    for name, sql in custom_checks:
        try:
            count = db.execute(sql).fetchone()[0]
            detail = "Passed" if count == 0 else f"{count} issue(s)"
            if name == "Child Star Balances" and count == 0:
                detail = "No negative balances"
            database_checks.append(item(name, "pass" if count == 0 else "fail", detail))
        except sqlite3.Error as exc:
            database_checks.append(item(name, "warning", f"Check unavailable: {exc}"))
    groups.append({"name": "Database & Family Data", "icon": "🗄️", "checks": database_checks})

    security_checks: list[dict[str, str | None]] = []

    # MGMT-0001: System Health belongs to the Application Owner and must not
    # require an active family session. Summarize family security across the
    # installation instead of resolving one tenant through get_current_family_id().
    active_family_count = db.execute(
        "SELECT COUNT(*) FROM families WHERE status='active'"
    ).fetchone()[0]
    families_with_pin = 0
    if _table_exists("family_security"):
        families_with_pin = db.execute(
            """SELECT COUNT(DISTINCT f.id)
               FROM families f
               JOIN family_security fs ON fs.family_id=f.id
               WHERE f.status='active'
                 AND fs.parent_pin_hash IS NOT NULL
                 AND fs.parent_pin_hash<>''"""
        ).fetchone()[0]
    families_without_pin = max(0, active_family_count - families_with_pin)
    security_checks.append(item(
        "Parent PIN Coverage",
        "pass" if active_family_count > 0 and families_without_pin == 0 else "warning",
        (
            f"Configured for all {active_family_count} active families"
            if active_family_count > 0 and families_without_pin == 0
            else (
                f"{families_with_pin} of {active_family_count} active families configured"
                if active_family_count > 0
                else "No active families"
            )
        ),
        action_url="developer.families",
        action_text="Manage Families",
    ))

    owner_setting = db.execute(
        "SELECT value FROM settings WHERE key='installation_owner_account_id' AND value<>''"
    ).fetchone() if _table_exists("settings") else None
    security_checks.append(item(
        "Installation Owner",
        "pass" if owner_setting else "warning",
        "Configured" if owner_setting else "Not yet assigned",
        action_url="developer.settings",
        action_text="Open Developer Settings",
    ))

    registration_row = db.execute(
        "SELECT value FROM settings WHERE key='registration_mode' AND value<>''"
    ).fetchone() if _table_exists("settings") else None
    registration_mode = str(registration_row[0]).title() if registration_row else "Not configured"
    security_checks.append(item(
        "Registration Mode",
        "pass" if registration_row else "warning",
        registration_mode,
        action_url="developer.settings",
        action_text="Open Developer Settings",
    ))
    groups.append({"name": "Security & Configuration", "icon": "🛡️", "checks": security_checks})

    content_checks: list[dict[str, str | None]] = []
    from services.content_packs import ensure_content_pack_tables
    ensure_content_pack_tables()

    families_with_default_pack = db.execute(
        """SELECT COUNT(DISTINCT fcp.family_id)
           FROM family_content_packs fcp
           JOIN families f ON f.id=fcp.family_id
           WHERE f.status='active'
             AND fcp.pack_key='explorer_starter'
             AND fcp.status='active'"""
    ).fetchone()[0]
    families_without_default_pack = max(
        0, active_family_count - families_with_default_pack
    )
    content_checks.append(item(
        "Default Content Pack Coverage",
        "pass" if active_family_count > 0 and families_without_default_pack == 0 else "warning",
        (
            f"Installed for all {active_family_count} active families"
            if active_family_count > 0 and families_without_default_pack == 0
            else (
                f"{families_with_default_pack} of {active_family_count} active families installed"
                if active_family_count > 0
                else "No active families"
            )
        ),
        action_url="developer.packs",
        action_text="Manage Packs",
    ))

    installed_count = db.execute(
        """SELECT COUNT(*)
           FROM family_content_packs fcp
           JOIN families f ON f.id=fcp.family_id
           WHERE f.status='active' AND fcp.status='active'"""
    ).fetchone()[0]
    content_checks.append(item(
        "Installed Content Packs",
        "pass" if installed_count > 0 else "warning",
        f"{installed_count} active installation(s) across all families",
        action_url="developer.packs",
        action_text="Manage Packs",
    ))
    groups.append({"name": "Content", "icon": "📦", "checks": content_checks})

    backup_checks: list[dict[str, str | None]] = []
    backups = list_backups()
    if backups:
        latest = backups[0]
        backup_checks.append(item(
            "Database Backup",
            "pass",
            f"Latest: {latest['created_at']} ({latest['size_text']})",
            action_url="maintenance.center",
            action_text="Manage Backups",
        ))
    else:
        backup_checks.append(item(
            "Database Backup",
            "warning",
            "No backups have been created",
            action_url="maintenance.center",
            action_text="Create Backup",
        ))
    groups.append({"name": "Recovery", "icon": "💾", "checks": backup_checks})

    all_checks = [check for group in groups for check in group["checks"]]
    counts = {
        "pass": sum(1 for check in all_checks if check["status"] == "pass"),
        "warning": sum(1 for check in all_checks if check["status"] == "warning"),
        "fail": sum(1 for check in all_checks if check["status"] == "fail"),
    }
    if counts["fail"]:
        overall_status = "attention"
        overall_label = "Attention Required"
    elif counts["warning"]:
        overall_status = "warning"
        overall_label = "Healthy with Warnings"
    else:
        overall_status = "healthy"
        overall_label = "Healthy"

    return {
        "groups": groups,
        "counts": counts,
        "overall_status": overall_status,
        "overall_label": overall_label,
        "checked_at": checked_at.strftime("%B %d, %Y at %I:%M %p").replace(" 0", " "),
        "application_version": str(current_app.config.get("APP_VERSION", "Unknown")),
        "database_schema": "SQLite / current schema",
        "active_family_count": active_family_count,
    }

