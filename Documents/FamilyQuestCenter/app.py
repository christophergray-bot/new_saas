"""Family Quest Center developer documentation.

File: app.py
Purpose: Creates and configures the Flask application, registers routes, and starts the local server.

Maintenance notes:
- Preserve tenant and family data isolation when changing queries.
- Keep route, template, and schema changes synchronized.
- Run regression tests before release packaging.
Documentation updated: 2026-07-31.
"""

from flask import Flask, session, request, render_template, redirect, url_for
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.exceptions import HTTPException

from config import Config
from database import get_db, get_engine, init_app, is_postgres
from routes.auth import auth_blueprint, init_parent_security
from routes.account import account_blueprint
from routes.approvals import approvals_blueprint
from routes.child import child_blueprint
from routes.children import children_blueprint
from routes.developer import developer_blueprint
from routes.home import home_blueprint
from routes.missions import missions_blueprint
from routes.parent import parent_blueprint
from routes.quests import quests_blueprint
from routes.reward_shop import reward_shop_blueprint
from routes.rewards import rewards_blueprint
from routes.adventures import parent_adventures_blueprint, child_adventures_blueprint
from routes.notifications import notifications_blueprint
from routes.reports import reports_blueprint
from routes.maintenance import maintenance_blueprint
from routes.achievements import achievements_blueprint
from routes.archive import archive_blueprint
from routes.journeys import journeys_blueprint
from routes.parent_management import parent_management_blueprint
from routes.content_packs import content_packs_blueprint
from routes.onboarding import onboarding_blueprint
from routes.billing import billing_blueprint

APP_VERSION = "1.7.0-rc1"


def create_app(config_overrides=None) -> Flask:
    """Create and configure the Flask application.

    ``config_overrides`` allows tests and alternate local installations to
    supply isolated database, backup, and security settings without mutating
    the process-wide Config class or relying on import-time environment values.
    """
    app = Flask(__name__)
    app.config.from_object(Config)
    if config_overrides:
        app.config.update(config_overrides)
    if app.config.get("IS_PRODUCTION"):
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
    app.config.setdefault("MAX_CONTENT_LENGTH", 4 * 1024 * 1024)
    app.config.setdefault("APP_VERSION", APP_VERSION)

    init_app(app)

    from services.security import (
        apply_security_headers,
        get_csrf_token,
        validate_csrf_request,
    )
    from services.input_validation import validate_common_form_input
    app.jinja_env.globals["csrf_token"] = get_csrf_token
    app.before_request(validate_common_form_input)
    app.before_request(validate_csrf_request)
    app.after_request(apply_security_headers)

    init_parent_security(app)

    # Initialize the selected database backend. Local development keeps SQLite;
    # Railway staging/production use DATABASE_URL and PostgreSQL.
    with app.app_context():
        if is_postgres():
            from init_db import initialize_postgres_database
            initialize_postgres_database(get_engine())
        else:
            database_path = app.config["DATABASE_PATH"]
            if not database_path.exists():
                from init_db import initialize_database
                initialize_database(database_path)

            from services.multifamily_foundation import ensure_multifamily_foundation
            ensure_multifamily_foundation(database_path)
            from services.mission_tenant_isolation import ensure_mission_tenant_isolation
            ensure_mission_tenant_isolation(database_path)
            from services.default_achievements import ensure_core_achievements
            ensure_core_achievements(database_path)
            from services.onboarding import ensure_onboarding_schema
            ensure_onboarding_schema(database_path)

        from services.billing import ensure_billing_schema
        ensure_billing_schema()

    app.register_blueprint(home_blueprint)
    app.register_blueprint(account_blueprint)
    app.register_blueprint(auth_blueprint)
    app.register_blueprint(parent_blueprint)
    app.register_blueprint(children_blueprint)
    app.register_blueprint(child_blueprint)
    app.register_blueprint(reward_shop_blueprint)
    app.register_blueprint(developer_blueprint)
    app.register_blueprint(quests_blueprint)
    app.register_blueprint(missions_blueprint)
    app.register_blueprint(approvals_blueprint)
    app.register_blueprint(rewards_blueprint)
    app.register_blueprint(parent_adventures_blueprint)
    app.register_blueprint(child_adventures_blueprint)
    app.register_blueprint(notifications_blueprint)
    app.register_blueprint(reports_blueprint)
    app.register_blueprint(maintenance_blueprint)
    app.register_blueprint(achievements_blueprint)
    app.register_blueprint(archive_blueprint)
    app.register_blueprint(journeys_blueprint)
    app.register_blueprint(parent_management_blueprint)
    app.register_blueprint(content_packs_blueprint)
    app.register_blueprint(onboarding_blueprint)
    app.register_blueprint(billing_blueprint)

    @app.before_request
    def enforce_subscription_access():
        """Lock paid application features when subscription enforcement is enabled."""
        if not app.config.get("STRIPE_ENFORCE_SUBSCRIPTIONS"):
            return None
        endpoint = request.endpoint or ""
        allowed_prefixes = ("billing.", "account.", "auth.", "home.", "static")
        if endpoint.startswith(allowed_prefixes):
            return None
        from services.account_auth import get_current_account, get_current_membership
        account = get_current_account()
        membership = get_current_membership() if account is not None else None
        if membership is None:
            return None
        from services.billing import family_has_access
        if not family_has_access(int(membership["family_id"])):
            return redirect(url_for("billing.status"))
        return None

    @app.context_processor
    def inject_application_shell():
        """Provide shell data without requiring tenant context on public pages."""
        from models.settings import get_public_settings
        from services.account_auth import get_current_account, get_current_membership, is_installation_owner

        account = get_current_account()
        membership = get_current_membership() if account is not None else None

        # A stale browser session must never break the public website or error pages.
        if membership is None:
            session.pop("parent_authenticated", None)

        pending_quests = 0
        pending_rewards = 0
        notification_count = 0

        # Tenant-scoped shell queries are only valid after both account and family
        # membership have been resolved and the parent area has been unlocked.
        if membership is not None and session.get("parent_authenticated"):
            family_id = int(membership["family_id"])
            database = get_db()
            pending_quests = database.execute(
                "SELECT COUNT(*) FROM assignments WHERE status = 'completed' AND family_id = ?",
                (family_id,),
            ).fetchone()[0]
            pending_rewards = database.execute(
                "SELECT COUNT(*) FROM reward_requests WHERE status = 'pending' AND family_id = ?",
                (family_id,),
            ).fetchone()[0]

            from services.content_packs import list_pending_pack_requests
            pending_quests += len(list_pending_pack_requests())

            from models.notifications import get_parent_notifications
            notification_count = len(get_parent_notifications())

        setup_pending = False
        if membership is not None and session.get("parent_authenticated"):
            try:
                from services.onboarding import family_setup_complete
                setup_pending = not family_setup_complete()
            except Exception:
                setup_pending = False

        from models.settings import get_registration_mode, registration_is_enabled
        effective_registration_mode = get_registration_mode(app.config["REGISTRATION_MODE"])
        shell_settings = get_public_settings()

        # FC-0033 / Priority 15: resolve one Home destination by the active role.
        # This value is used by both the Family Quest Center logo and the first
        # navigation link so those controls can never disagree.
        developer_access = is_installation_owner() if account is not None else False
        active_child_id = session.get("active_child_id")
        active_child = None
        if membership is not None and active_child_id is not None:
            active_child = get_db().execute(
                """SELECT id
                   FROM users
                   WHERE id=? AND family_id=? AND role='child' AND active=1""",
                (int(active_child_id), int(membership["family_id"])),
            ).fetchone()
            if active_child is None:
                session.pop("active_child_id", None)

        if developer_access:
            role_home_url = url_for("developer.dashboard")
            role_home_label = "Owner Dashboard"
            role_home_icon = "🛠️"
        elif active_child is not None:
            role_home_url = url_for("child.dashboard", user_id=int(active_child["id"]))
            role_home_label = "My Day"
            role_home_icon = "📋"
        elif membership is not None:
            role_home_url = url_for("parent.dashboard")
            role_home_label = "Parent Dashboard"
            role_home_icon = "🛡️"
        else:
            role_home_url = url_for("home.index")
            role_home_label = "Home"
            role_home_icon = "🏠"

        return {
            "csrf_token_value": get_csrf_token(),
            "current_account": account,
            "current_membership": membership,
            "setup_pending": setup_pending,
            "app_version": app.config["APP_VERSION"],
            "application_name": shell_settings["application_name"],
            "family_name": shell_settings["family_name"],
            "pending_quest_count": pending_quests,
            "pending_reward_count": pending_rewards,
            "parent_notification_count": notification_count,
            "registration_mode": effective_registration_mode,
            "registration_enabled": registration_is_enabled(app.config["REGISTRATION_MODE"]),
            "billing_checkout_enabled": bool(
                app.config.get("PAYMENTS_MODE") in {"test", "live"}
                and app.config.get("STRIPE_SECRET_KEY")
                and app.config.get("STRIPE_PRICE_ID")
            ),
            "developer_access": developer_access,
            "role_home_url": role_home_url,
            "role_home_label": role_home_label,
            "role_home_icon": role_home_icon,
        }


    @app.errorhandler(400)
    def bad_request(error):
        """Show a safe message for invalid or expired request tokens."""
        return render_template("errors/400.html"), 400

    @app.errorhandler(Exception)
    def log_unhandled_exception(error):
        """Handle the log unhandled exception workflow."""
        if isinstance(error, HTTPException):
            if error.code == 404:
                return render_template("errors/404.html"), 404
            return error

        from traceback import format_exc
        from models.administration import record_error

        record_error(
            type(error).__name__,
            str(error),
            traceback_text=format_exc(),
            request_path=request.path,
        )
        app.logger.exception("Unhandled application error")
        return render_template("errors/500.html"), 500

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=app.config.get("DEBUG", False))
