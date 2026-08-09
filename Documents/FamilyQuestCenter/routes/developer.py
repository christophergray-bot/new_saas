"""Family Quest Center developer documentation.

File: routes/developer.py
Purpose: Defines Flask routes and request-handling workflows for developer features.

Maintenance notes:
- Preserve tenant and family data isolation when changing queries.
- Keep route, template, and schema changes synchronized.
- Run regression tests before release packaging.
Documentation updated: 2026-07-31.
"""

from flask import Blueprint, Response, abort, current_app, flash, redirect, render_template, request, url_for

from models.settings import get_registration_mode, get_global_setting, set_global_setting
from services.account_auth import get_current_account, is_installation_owner
from services.account_tokens import application_url, create_password_reset_token
from services.email_service import EmailConfigurationError, EmailDeliveryError, send_email, email_configuration_status

from models.administration import (
    clear_error_entries,
    set_error_resolved,
    database_statistics,
    diagnostic_snapshot,
    get_application_info,
    get_audit_entries,
    audit_summary,
    get_error_entries,
    get_migration_history,
    runtime_information,
    system_health,
    validate_content,
    log_audit,
    platform_overview,
    platform_attention_items,
    platform_health_summary,
    list_platform_families,
    get_platform_family_detail,
    perform_family_admin_action,
    list_platform_parent_accounts,
    get_platform_parent_account_detail,
    perform_parent_account_admin_action,
    platform_report,
    platform_reports_dashboard,
    platform_subscription_management,
)


developer_blueprint = Blueprint("developer", __name__, url_prefix="/developer")

@developer_blueprint.before_request
def require_installation_owner():
    """Keep installation-level developer tools limited to the designated owner."""
    if not is_installation_owner():
        abort(403)



@developer_blueprint.route("/")
def dashboard():
    """Handle the dashboard workflow."""
    return render_template(
        "developer/dashboard.html",
        overview=platform_overview(),
        attention_items=platform_attention_items(),
        health_summary=platform_health_summary(),
        recent_activity=get_audit_entries(limit=30),
    )



def _render_owner_section(title: str, subtitle: str, eyebrow: str, next_phase: str):
    return render_template(
        "developer/section_placeholder.html",
        title=title, subtitle=subtitle, eyebrow=eyebrow, next_phase=next_phase,
    )


@developer_blueprint.route("/families")
def families():
    search = request.args.get("q", "").strip()
    status = request.args.get("status", "all").strip().lower()
    subscription = request.args.get("subscription", "all").strip().lower()
    sort = request.args.get("sort", "newest").strip().lower()
    return render_template("developer/families.html", families=list_platform_families(search, status, subscription, sort),
                           search=search, selected_status=status, selected_subscription=subscription, selected_sort=sort)


@developer_blueprint.route("/families/<int:family_id>")
def family_detail(family_id):
    detail = get_platform_family_detail(family_id)
    if detail is None:
        abort(404)
    return render_template("developer/family_detail.html", **detail)


@developer_blueprint.route("/families/<int:family_id>/action", methods=["POST"])
def family_action(family_id):
    action = request.form.get("action", "").strip().lower()
    confirmation = request.form.get("confirm", "").strip().lower()
    if confirmation != "confirm":
        flash("Type CONFIRM to complete this administrative action.", "error")
        return redirect(url_for("developer.family_detail", family_id=family_id))
    account = get_current_account()
    try:
        detail = perform_family_admin_action(family_id, action, account["display_name"] if account else "Application Owner")
    except (LookupError, ValueError) as exc:
        flash(str(exc), "error")
    else:
        flash(detail, "success")
    return redirect(url_for("developer.family_detail", family_id=family_id))


@developer_blueprint.route("/parent-accounts")
def parent_accounts():
    search = request.args.get("q", "").strip()
    status = request.args.get("status", "all").strip().lower()
    role = request.args.get("role", "all").strip().lower()
    email_status = request.args.get("email_status", "all").strip().lower()
    sort = request.args.get("sort", "name").strip().lower()
    accounts = list_platform_parent_accounts(search, status, role, email_status, sort)
    return render_template("developer/parent_accounts.html", accounts=accounts, search=search,
                           selected_status=status, selected_role=role, selected_email_status=email_status,
                           selected_sort=sort)


@developer_blueprint.route("/parent-accounts/<int:account_id>")
def parent_account_detail(account_id):
    detail = get_platform_parent_account_detail(account_id)
    if detail is None:
        abort(404)
    return render_template("developer/parent_account_detail.html", **detail)


@developer_blueprint.route("/parent-accounts/<int:account_id>/action", methods=["POST"])
def parent_account_action(account_id):
    action = request.form.get("action", "").strip().lower()
    account = get_current_account()
    if action == "password_reset":
        detail = get_platform_parent_account_detail(account_id)
        if detail is None:
            abort(404)
        target = detail["parent_account"]
        token = create_password_reset_token(account_id)
        reset_url = application_url(url_for("account.reset_password", token=token))
        text = (f"Hello {target['display_name']},\n\n"
                "The Family Quest Center Application Owner sent you a password reset link.\n\n"
                f"Reset your password: {reset_url}\n\nThis one-time link expires in 60 minutes.")
        html = f"<h2>Family Quest Center Password Reset</h2><p>Hello {target['display_name']},</p><p><a href='{reset_url}'>Reset your password</a></p><p>This one-time link expires in 60 minutes.</p>"
        try:
            send_email(recipients=target["email"], subject="Reset your Family Quest Center password", text_body=text, html_body=html)
        except (EmailConfigurationError, EmailDeliveryError) as exc:
            flash(str(exc), "error")
        else:
            log_audit("parent_account_password_reset_sent", "parent_account", account_id,
                      details=f"Password reset sent to {target['email']}", actor_type="application_owner",
                      actor_name=account["display_name"] if account else "Application Owner")
            flash("Password reset email sent.", "success")
        return redirect(url_for("developer.parent_account_detail", account_id=account_id))

    confirmation = request.form.get("confirm", "").strip().lower()
    if action in {"disable", "reactivate", "verify_email", "force_logout", "unlock"} and confirmation != "confirm":
        flash("Type CONFIRM to complete this administrative action.", "error")
        return redirect(url_for("developer.parent_account_detail", account_id=account_id))
    try:
        message = perform_parent_account_admin_action(account_id, action, account["display_name"] if account else "Application Owner")
    except (LookupError, ValueError) as exc:
        flash(str(exc), "error")
    else:
        flash(message, "success")
    return redirect(url_for("developer.parent_account_detail", account_id=account_id))


@developer_blueprint.route("/subscriptions")
def subscriptions():
    """Monitor installation-wide family subscription and billing status."""
    search = request.args.get("q", "").strip()
    status = request.args.get("status", "all").strip().lower()
    sort = request.args.get("sort", "attention").strip().lower()
    data = platform_subscription_management(search, status, sort)
    return render_template(
        "developer/subscriptions.html",
        **data,
        payments_mode=current_app.config.get("PAYMENTS_MODE", "disabled"),
        stripe_configured=bool(
            current_app.config.get("STRIPE_SECRET_KEY")
            and current_app.config.get("STRIPE_PRICE_ID")
        ),
    )


@developer_blueprint.route("/packs")
def packs():
    return _render_owner_section("Packs", "Manage Quest, Adventure, Avatar, Theme, Frame, and future content packs.", "CONTENT MANAGEMENT", "Pack Store and Approval phase")


@developer_blueprint.route("/reports")
def reports():
    return render_template("developer/reports.html", report_cards=platform_reports_dashboard())


@developer_blueprint.route("/reports/<report_key>")
def report_detail(report_key):
    start_date = request.args.get("start_date", "").strip() or None
    end_date = request.args.get("end_date", "").strip() or None
    try:
        report = platform_report(report_key, start_date, end_date)
    except LookupError:
        abort(404)
    return render_template("developer/report_detail.html", report=report)


@developer_blueprint.route("/reports/<report_key>.csv")
def report_csv(report_key):
    import csv
    import io
    start_date = request.args.get("start_date", "").strip() or None
    end_date = request.args.get("end_date", "").strip() or None
    try:
        report = platform_report(report_key, start_date, end_date)
    except LookupError:
        abort(404)
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=report["columns"], extrasaction="ignore")
    writer.writeheader()
    writer.writerows(report["rows"])
    return Response(output.getvalue(), mimetype="text/csv", headers={"Content-Disposition": f"attachment; filename={report_key}.csv"})


@developer_blueprint.route("/operations")
def operations():
    from models.reliability import list_backups
    backups = list_backups()
    errors = get_error_entries(limit=8)
    unresolved_errors = sum(1 for row in errors if not row["resolved"])
    email_status = email_configuration_status()
    return render_template(
        "developer/operations.html",
        health_checks=system_health(),
        recent_errors=errors,
        unresolved_errors=unresolved_errors,
        backups=backups[:5],
        backup_count=len(backups),
        statistics=database_statistics(),
        migrations=get_migration_history()[:5],
        recent_audit=get_audit_entries(limit=8),
        audit_summary=audit_summary(),
        email_status=email_status,
        payments_mode=current_app.config.get("PAYMENTS_MODE", "disabled"),
    )


@developer_blueprint.route("/settings", methods=["GET", "POST"])
def settings():
    """Manage safe installation-level settings without exposing secrets."""
    account = get_current_account()
    actor_name = account["display_name"] if account else "Application Owner"

    if request.method == "POST":
        section = request.form.get("section", "").strip().lower()
        changes: dict[str, str] = {}
        try:
            if section == "general":
                changes = {
                    "system_application_name": request.form.get("application_name", "").strip()[:100],
                    "company_name": request.form.get("company_name", "").strip()[:120],
                    "support_email": request.form.get("support_email", "").strip()[:254],
                    "contact_website": request.form.get("contact_website", "").strip()[:300],
                }
                if not changes["system_application_name"]:
                    raise ValueError("Application name is required.")
                if changes["support_email"] and "@" not in changes["support_email"]:
                    raise ValueError("Enter a valid support email address.")
            elif section == "registration":
                mode = request.form.get("registration_mode", "").strip().lower()
                if mode not in {"local", "closed", "open", "trial"}:
                    raise ValueError("Choose a valid registration mode.")
                trial_days = int(request.form.get("default_trial_days", "14"))
                if not 0 <= trial_days <= 365:
                    raise ValueError("Trial length must be between 0 and 365 days.")
                changes = {
                    "registration_mode": mode,
                    "require_email_verification": "1" if request.form.get("require_email_verification") else "0",
                    "default_trial_days": str(trial_days),
                    "default_starter_pack": request.form.get("default_starter_pack", "").strip()[:100],
                }
            elif section == "subscription":
                grace_days = int(request.form.get("subscription_grace_days", "7"))
                if not 0 <= grace_days <= 90:
                    raise ValueError("Grace period must be between 0 and 90 days.")
                changes = {
                    "billing_enabled": "1" if request.form.get("billing_enabled") else "0",
                    "trial_enabled": "1" if request.form.get("trial_enabled") else "0",
                    "subscription_grace_days": str(grace_days),
                    "default_plan": request.form.get("default_plan", "monthly").strip()[:50],
                }
            elif section == "security":
                timeout = int(request.form.get("platform_session_timeout_minutes", "60"))
                attempts = int(request.form.get("maximum_login_attempts", "5"))
                lockout = int(request.form.get("account_lockout_minutes", "15"))
                remember_days = int(request.form.get("remember_me_days", "30"))
                pin_length = int(request.form.get("parent_pin_min_length", "4"))
                if not 5 <= timeout <= 1440:
                    raise ValueError("Session timeout must be between 5 and 1,440 minutes.")
                if not 3 <= attempts <= 20:
                    raise ValueError("Maximum login attempts must be between 3 and 20.")
                if not 1 <= lockout <= 1440:
                    raise ValueError("Lockout duration must be between 1 and 1,440 minutes.")
                if not 1 <= remember_days <= 365:
                    raise ValueError("Remember Me duration must be between 1 and 365 days.")
                if not 4 <= pin_length <= 12:
                    raise ValueError("Parent PIN length must be between 4 and 12 digits.")
                changes = {
                    "platform_session_timeout_minutes": str(timeout),
                    "maximum_login_attempts": str(attempts),
                    "account_lockout_minutes": str(lockout),
                    "remember_me_days": str(remember_days),
                    "parent_pin_min_length": str(pin_length),
                }
            elif section == "maintenance":
                enabled = bool(request.form.get("maintenance_mode"))
                confirmation = request.form.get("confirm", "").strip().lower()
                if enabled and confirmation != "confirm":
                    raise ValueError("Type CONFIRM before enabling maintenance mode.")
                changes = {
                    "maintenance_mode": "1" if enabled else "0",
                    "maintenance_allow_registration": "1" if request.form.get("maintenance_allow_registration") else "0",
                    "maintenance_message": request.form.get("maintenance_message", "").strip()[:500],
                }
            else:
                raise ValueError("Choose a valid settings section.")
        except (TypeError, ValueError) as exc:
            flash(str(exc), "error")
        else:
            changed = []
            for key, new_value in changes.items():
                old_value = str(get_global_setting(key, ""))
                if old_value != str(new_value):
                    set_global_setting(key, str(new_value))
                    changed.append(f"{key}: {old_value or '(blank)'} -> {new_value or '(blank)'}")
            if changed:
                log_audit(
                    "system_settings_updated", "system_settings", None,
                    details=f"Section {section}; " + "; ".join(changed),
                    actor_type="application_owner", actor_name=actor_name,
                )
                flash(f"{section.title()} settings saved.", "success")
            else:
                flash("No settings changed.", "info")
            return redirect(url_for("developer.settings", section=section))

    values = {
        key: get_global_setting(key, default)
        for key, default in {
            "system_application_name": "Family Quest Center",
            "company_name": "Family Quest Center LLC",
            "support_email": "",
            "contact_website": "",
            "registration_mode": get_registration_mode(current_app.config["REGISTRATION_MODE"]),
            "require_email_verification": "0",
            "default_trial_days": "14",
            "default_starter_pack": "",
            "billing_enabled": "0",
            "trial_enabled": "0",
            "subscription_grace_days": str(current_app.config.get("SUBSCRIPTION_GRACE_DAYS", 7)),
            "default_plan": "monthly",
            "platform_session_timeout_minutes": "60",
            "maximum_login_attempts": "5",
            "account_lockout_minutes": "15",
            "remember_me_days": "30",
            "parent_pin_min_length": "4",
            "maintenance_mode": "0",
            "maintenance_allow_registration": "0",
            "maintenance_message": "Family Quest Center is temporarily unavailable for scheduled maintenance.",
        }.items()
    }
    email_status = email_configuration_status()
    health_issues = []
    if not values["support_email"]:
        health_issues.append("Support email is not configured.")
    if not email_status["configured"]:
        health_issues.append("Outbound email is not fully configured.")
    if current_app.config.get("PAYMENTS_MODE") == "disabled":
        health_issues.append("Stripe billing is disabled.")
    if values["registration_mode"] in {"open", "trial"} and values["require_email_verification"] != "1":
        health_issues.append("Registration is enabled without required email verification.")

    return render_template(
        "developer/settings.html",
        values=values,
        email_status=email_status,
        environment=current_app.config.get("ENVIRONMENT", "development"),
        app_version=current_app.config.get("APP_VERSION", "Unknown"),
        payments_mode=current_app.config.get("PAYMENTS_MODE", "disabled"),
        stripe_configured=bool(current_app.config.get("STRIPE_SECRET_KEY") and current_app.config.get("STRIPE_PRICE_ID")),
        health_issues=health_issues,
        selected_section=request.args.get("section", "general"),
    )

@developer_blueprint.route("/health")
def health():
    """Handle the health workflow."""
    return render_template(
        "developer/health.html",
        health_checks=system_health(),
        runtime=runtime_information(),
        statistics=database_statistics(),
    )


@developer_blueprint.route("/migrations")
def migrations():
    """Handle the migrations workflow."""
    return render_template(
        "developer/migrations.html",
        migrations=get_migration_history(),
        application_info=get_application_info(),
    )


@developer_blueprint.route("/audit-log")
def audit_log():
    """Search and filter the installation-wide Audit Center."""
    filters = {
        "search": request.args.get("q", "").strip() or None,
        "action": request.args.get("action", "").strip() or None,
        "category": request.args.get("category", "all").strip().lower(),
        "start_date": request.args.get("start_date", "").strip() or None,
        "end_date": request.args.get("end_date", "").strip() or None,
    }
    entries = get_audit_entries(limit=500, action=filters["action"], search=filters["search"],
                                category=filters["category"], start_date=filters["start_date"],
                                end_date=filters["end_date"])
    return render_template("developer/audit_log.html", entries=entries, filters=filters,
                           summary=audit_summary())


@developer_blueprint.route("/audit-log.csv")
def audit_log_csv():
    """Export the currently filtered audit view as CSV."""
    import csv
    import io
    filters = {
        "search": request.args.get("q", "").strip() or None,
        "action": request.args.get("action", "").strip() or None,
        "category": request.args.get("category", "all").strip().lower(),
        "start_date": request.args.get("start_date", "").strip() or None,
        "end_date": request.args.get("end_date", "").strip() or None,
    }
    entries = get_audit_entries(limit=5000, action=filters["action"], search=filters["search"],
                                category=filters["category"], start_date=filters["start_date"],
                                end_date=filters["end_date"])
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["Date", "Actor Type", "Actor", "Action", "Entity Type", "Entity ID", "Family ID", "Details"])
    for row in entries:
        writer.writerow([row["created_at"], row["actor_type"], row["actor_name"], row["action"],
                         row["entity_type"], row["entity_id"], row["family_id"], row["details"]])
    return Response(output.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=family-quest-center-audit.csv"})


@developer_blueprint.route("/errors")
def errors():
    """Handle the errors workflow."""
    return render_template("developer/errors.html", entries=get_error_entries(limit=250))




@developer_blueprint.route("/errors/<int:error_id>/status", methods=["POST"])
def error_status(error_id):
    """Resolve or reopen a recorded application error."""
    resolved = request.form.get("status", "resolved") == "resolved"
    if not set_error_resolved(error_id, resolved):
        abort(404)
    account = get_current_account()
    log_audit("application_error_resolved" if resolved else "application_error_reopened",
              "error_log", error_id, actor_type="application_owner",
              actor_name=account["display_name"] if account else "Application Owner")
    flash("Error marked resolved." if resolved else "Error reopened.", "success")
    return redirect(url_for("developer.errors"))


@developer_blueprint.route("/errors/clear", methods=["POST"])
def clear_errors():
    """Handle the clear errors workflow."""
    count = clear_error_entries()
    flash(f"Cleared {count} error log entr{'y' if count == 1 else 'ies'}.", "success")
    return redirect(url_for("developer.errors"))


@developer_blueprint.route("/content")
def content_validator():
    """Handle the content validator workflow."""
    return render_template("developer/content.html", results=validate_content())


@developer_blueprint.route("/configuration")
def configuration():
    """Handle the configuration workflow."""
    return render_template("developer/configuration.html", runtime=runtime_information())



@developer_blueprint.route("/diagnostics")
def diagnostics():
    """Display a read-only support and release diagnostic snapshot."""
    return render_template("developer/diagnostics.html", snapshot=diagnostic_snapshot())


@developer_blueprint.route("/email-test", methods=["GET", "POST"])
def email_test():
    """Verify hosted SMTP delivery without exposing mail credentials."""
    from services.email_service import (
        EmailConfigurationError,
        EmailDeliveryError,
        email_configuration_status,
        send_email,
    )

    account = get_current_account()
    recipient = account["email"] if account is not None else ""
    status = email_configuration_status()

    if request.method == "POST":
        if not recipient:
            flash("The installation-owner account does not have an email address.", "error")
        else:
            app_url = current_app.config.get("APP_URL") or request.url_root.rstrip("/")
            try:
                send_email(
                    recipients=recipient,
                    subject="Family Quest Center email test",
                    text_body=(
                        "Family Quest Center successfully connected to the configured email service.\n\n"
                        f"Application: {app_url}\n"
                        "This message was requested from the installation-owner Developer Center."
                    ),
                    html_body=(
                        "<h2>Family Quest Center email test</h2>"
                        "<p>Family Quest Center successfully connected to the configured email service.</p>"
                        f"<p><strong>Application:</strong> {app_url}</p>"
                        "<p>This message was requested from the installation-owner Developer Center.</p>"
                    ),
                )
                log_audit(
                    "email_test_sent",
                    entity_type="system",
                    details=f"Test email sent to installation owner {recipient}",
                    actor_type="installation_owner",
                    actor_name=account["display_name"] or "Installation Owner",
                )
                flash(f"Test email sent to {recipient}.", "success")
                return redirect(url_for("developer.email_test"))
            except EmailConfigurationError as exc:
                flash(str(exc), "error")
            except EmailDeliveryError as exc:
                flash(str(exc), "error")

    return render_template(
        "developer/email_test.html",
        email_status=status,
        recipient=recipient,
    )
