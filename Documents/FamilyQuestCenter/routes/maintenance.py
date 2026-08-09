"""Family Quest Center developer documentation.

File: routes/maintenance.py
Purpose: Defines Flask routes and request-handling workflows for maintenance features.

Maintenance notes:
- Preserve tenant and family data isolation when changing queries.
- Keep route, template, and schema changes synchronized.
- Run regression tests before release packaging.
Documentation updated: 2026-07-31.
"""

from flask import Blueprint, flash, redirect, render_template, request, send_file, url_for

from database import close_db

from models.administration import log_audit
from services.account_auth import installation_owner_required, roles_required
from models.reliability import (
    build_export_zip,
    create_database_backup,
    delete_backup,
    get_backup_path,
    integrity_report,
    list_backups,
    restore_backup,
)

maintenance_blueprint = Blueprint("maintenance", __name__, url_prefix="/maintenance")


@maintenance_blueprint.route("/")
@installation_owner_required
def center():
    """Handle the center workflow."""
    return render_template("maintenance/center.html", backups=list_backups())


@maintenance_blueprint.route("/backup", methods=["POST"])
@installation_owner_required
def backup():
    """Handle the backup workflow."""
    path = create_database_backup()
    log_audit("database_backup_created", "backup", details=path.name)
    flash(f"Backup created: {path.name}", "success")
    return redirect(url_for("maintenance.center"))


@maintenance_blueprint.route("/backup/<name>/download")
@installation_owner_required
def download_backup(name):
    """Handle the download backup workflow."""
    return send_file(get_backup_path(name), as_attachment=True, download_name=name)


@maintenance_blueprint.route("/backup/<name>/delete", methods=["POST"])
@installation_owner_required
def remove_backup(name):
    """Handle the remove backup workflow."""
    delete_backup(name)
    log_audit("database_backup_deleted", "backup", details=name)
    flash("Backup deleted.", "success")
    return redirect(url_for("maintenance.center"))


@maintenance_blueprint.route("/backup/<name>/restore", methods=["POST"])
@installation_owner_required
def restore(name):
    """Handle the restore workflow."""
    confirmation = request.form.get("confirmation", "").strip().upper()
    if confirmation != "RESTORE":
        flash("Type RESTORE to confirm the database restore.", "error")
        return redirect(url_for("maintenance.center"))
    # Authentication and authorization checks may open the request-scoped
    # SQLite connection. Close it before restoring so Windows does not retain
    # a lock on the database. Flask teardown safely ignores the missing handle.
    close_db()
    safety_copy = restore_backup(name)
    flash(f"Database restored. A safety backup was created as {safety_copy.name}. Restart the application now.", "success")
    return redirect(url_for("maintenance.center"))


@maintenance_blueprint.route("/family-export")
@roles_required("owner", "parent")
def family_export():
    """Show the family-scoped export page without exposing installation backups."""
    return render_template("maintenance/family_export.html")


@maintenance_blueprint.route("/export")
@roles_required("owner", "parent")
def export_data():
    """Handle the export data workflow."""
    archive = build_export_zip()
    log_audit("family_data_exported", "export")
    return send_file(archive, as_attachment=True, download_name=archive.download_name, mimetype="application/zip")


@maintenance_blueprint.route("/integrity")
@installation_owner_required
def integrity():
    """Handle the integrity workflow."""
    return render_template("maintenance/integrity.html", report=integrity_report())
