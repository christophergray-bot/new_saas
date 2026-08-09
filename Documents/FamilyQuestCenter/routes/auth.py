"""Family Quest Center developer documentation.

File: routes/auth.py
Purpose: Defines Flask routes and request-handling workflows for auth features.

Maintenance notes:
- Preserve tenant and family data isolation when changing queries.
- Keep route, template, and schema changes synchronized.
- Run regression tests before release packaging.
Documentation updated: 2026-07-31.
"""

from functools import wraps
import time
from urllib.parse import urljoin, urlparse

from flask import (
    abort,
    Blueprint,
    current_app,
    Flask,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from services.account_auth import get_current_account, get_current_membership
from services.account_tokens import (
    application_url,
    consume_pin_reset,
    create_pin_reset_token,
    get_valid_pin_reset,
)
from services.email_service import EmailConfigurationError, EmailDeliveryError, send_email
from database import get_db
from models.administration import log_audit
from models.settings import get_int_setting

from services.family_security import get_parent_pin_hash, parent_pin_exists, set_parent_pin_hash
from services.security import (
    clear_rate_limit,
    client_ip,
    rate_limit_is_blocked,
    rate_limit_subject,
    record_rate_limit_failure,
    rotate_csrf_token,
)



auth_blueprint = Blueprint(
    "auth",
    __name__,
    url_prefix="/parent",
)


PROTECTED_PREFIXES = (
    "/parent",
    "/developer",
    "/quests",
    "/approvals",
    "/maintenance",
)

PUBLIC_ENDPOINTS = {
    "home.index",
    "home.register",
    "home.privacy",
    "home.terms",
    "home.contact",
    "auth.login",
    "auth.setup_pin",
    "auth.logout",
    "auth.reset_pin",
    "auth.complete_pin_reset",
    # Stripe checkout must be reachable before a customer has an account.
    # Billing status and the customer portal remain protected by @account_required.
    "billing.plans",
    "billing.create_checkout",
    "billing.success",
    "billing.cancel",
    "billing.webhook",
    "static",
    # Pack artwork is a static application asset. It must remain available
    # in Child Mode after Parent Area authorization is intentionally removed.
    "content_packs.asset",
}


def _valid_four_digit_pin(pin: str) -> bool:
    """Return True only for a four-digit numeric PIN."""

    return len(pin) == 4 and pin.isdigit()


def _safe_next_url(target: str | None) -> str | None:
    """Allow redirects only to local URLs on the same host."""

    if not target:
        return None

    host_url = urlparse(request.host_url)
    redirect_url = urlparse(urljoin(request.host_url, target))

    if (
        redirect_url.scheme in {"http", "https"}
        and redirect_url.netloc == host_url.netloc
    ):
        return redirect_url.path

    return None


def parent_required(view_function):
    """Protect an individual view with the parent session."""

    @wraps(view_function)
    def wrapped_view(*args, **kwargs):
        """Handle the wrapped view workflow."""
        if not session.get("parent_authenticated"):
            return redirect(
                url_for(
                    "auth.login",
                    next=request.full_path.rstrip("?"),
                )
            )

        return view_function(*args, **kwargs)

    return wrapped_view


def init_parent_security(app: Flask) -> None:
    """Protect parent and administrative routes."""

    @app.before_request
    def require_parent_session():
        """Handle the require parent session workflow."""
        endpoint = request.endpoint

        # Public marketing and account pages must remain available before sign-in.
        public_billing_paths = {
            "/billing",
            "/billing/",
            "/billing/checkout",
            "/billing/success",
            "/billing/cancel",
            "/billing/webhook",
        }
        if (
            endpoint in PUBLIC_ENDPOINTS
            or request.path in public_billing_paths
            or (endpoint and endpoint.startswith("account."))
            or endpoint == "parent_management.accept_invitation"
        ):
            return None

        account = get_current_account()

        # Platform-only routes use their own owner/account decorators and must not
        # require a family membership or Parent PIN.  This allows the separate
        # Application Owner account to operate without belonging to a family.
        if endpoint and (
            endpoint.startswith("developer.")
            or endpoint.startswith("maintenance.")
        ):
            if account is None:
                return redirect(url_for("account.login", next=request.full_path.rstrip("?")))
            return None

        # Family-facing routes require both a signed-in account and an active
        # family membership.
        membership = get_current_membership() if account is not None else None
        if account is None:
            return redirect(url_for("account.login", next=request.full_path.rstrip("?")))
        if membership is None:
            # MGMT-0005: an authenticated Application Owner (or any signed-in
            # account without an active family membership) is unauthorized for
            # family-facing routes, not unauthenticated.
            abort(403)

        # FC-0021 / ADJ-0015 / FQC-NEW-006:
        # Child Mode has its own long inactivity window. Entering a child-facing
        # route still atomically removes Parent Area authorization. A timed-out
        # Child Mode returns to the Family page; selecting an explorer there
        # starts a fresh child session without unlocking Parent Area.
        child_endpoint = bool(
            endpoint
            and (
                endpoint.startswith("child.")
                or endpoint.startswith("child_adventures.")
                or endpoint.startswith("reward_shop.")
                or endpoint in {
                    "onboarding.explorer_training",
                    "onboarding.complete_explorer_training",
                }
            )
        )
        if child_endpoint:
            now = int(time.time())
            child_timeout = max(
                3600,
                min(86400, get_int_setting("child_session_timeout_seconds", 43200)),
            )
            active_child_id = session.get("active_child_id")
            child_last_activity_at = session.get("child_last_activity_at")

            if active_child_id is not None and child_last_activity_at is not None:
                try:
                    expired = now - int(child_last_activity_at) > child_timeout
                except (TypeError, ValueError):
                    expired = True
                if expired:
                    session.pop("active_child_id", None)
                    session.pop("child_last_activity_at", None)
                    session.pop("parent_authenticated", None)
                    session.pop("parent_last_activity_at", None)
                    flash("Explorer session ended after inactivity. Choose an explorer to continue.", "info")
                    return redirect(url_for("home.family_dashboard"))

            user_id = (request.view_args or {}).get("user_id")
            # Some child actions identify the child indirectly through a
            # tenant-scoped assignment. Those actions must use the active child.
            if user_id is None:
                user_id = active_child_id
            if user_id is None:
                abort(400)

            child = get_db().execute(
                "SELECT id FROM users WHERE id=? AND family_id=? AND role='child' AND active=1",
                (int(user_id), int(membership["family_id"])),
            ).fetchone()
            if child is None:
                abort(404)

            session.pop("parent_authenticated", None)
            session.pop("parent_last_activity_at", None)
            session["active_child_id"] = int(user_id)
            session["child_last_activity_at"] = now
            return None

        path_is_protected = any(
            request.path == prefix
            or request.path.startswith(f"{prefix}/")
            for prefix in PROTECTED_PREFIXES
        )

        if not path_is_protected:
            return None

        if membership["role"] not in {"owner", "parent"}:
            abort(403)

        if not parent_pin_exists():
            return redirect(url_for("auth.setup_pin"))

        if not session.get("parent_authenticated"):
            return redirect(
                url_for(
                    "auth.login",
                    next=request.full_path.rstrip("?"),
                )
            )

        # FQC-NEW-006: Parent Area authorization uses its own short inactivity
        # timer and never inherits the much longer Child Mode timeout.
        now = int(time.time())
        parent_timeout = max(
            60,
            min(86400, get_int_setting("session_timeout_seconds", 600)),
        )
        parent_last_activity_at = session.get("parent_last_activity_at")
        if parent_last_activity_at is not None:
            try:
                parent_expired = now - int(parent_last_activity_at) > parent_timeout
            except (TypeError, ValueError):
                parent_expired = True
            if parent_expired:
                session.pop("parent_authenticated", None)
                session.pop("parent_last_activity_at", None)
                flash("Parent Area locked after inactivity.", "info")
                return redirect(
                    url_for(
                        "auth.login",
                        next=request.full_path.rstrip("?"),
                    )
                )

        session["parent_last_activity_at"] = now
        return None


@auth_blueprint.route("/setup-pin", methods=["GET", "POST"])
def setup_pin():
    """Create the first parent PIN."""

    if get_current_account() is None or get_current_membership() is None:
        return redirect(url_for("account.login", next=request.full_path.rstrip("?")))

    if parent_pin_exists():
        if session.get("parent_authenticated"):
            return redirect(url_for("parent.settings"))

        return redirect(url_for("auth.login"))

    # Only Parent One may create the shared PIN when a family does not yet have one.
    if get_current_membership()["role"] != "owner":
        abort(403)

    if request.method == "POST":
        membership = get_current_membership()
        pin_subject = rate_limit_subject(client_ip(), membership["family_id"] if membership else "unknown")
        blocked, remaining = rate_limit_is_blocked("parent_pin_setup", pin_subject)
        if blocked:
            flash(f"Too many PIN attempts. Try again in about {max(1, remaining // 60 + 1)} minute(s).", "error")
            return render_template("parent/setup_pin.html"), 429
        pin = request.form.get("pin", "").strip()
        confirm_pin = request.form.get("confirm_pin", "").strip()

        if not _valid_four_digit_pin(pin):
            flash("The parent PIN must contain exactly four digits.", "error")
        elif pin != confirm_pin:
            flash("The PIN entries do not match.", "error")
        else:
            set_parent_pin_hash(generate_password_hash(pin))
            session["parent_authenticated"] = True
            session["parent_last_activity_at"] = int(time.time())
            session.permanent = True
            rotate_csrf_token()
            clear_rate_limit("parent_pin_setup", pin_subject)
            flash("Parent PIN created successfully.", "success")
            return redirect(url_for("onboarding.family_setup"))

    if request.method == "POST":
        record_rate_limit_failure(
            "parent_pin_setup", pin_subject, max_attempts=8, window_seconds=900, block_seconds=900
        )
    return render_template("parent/setup_pin.html")


@auth_blueprint.route("/reset-pin", methods=["GET", "POST"])
def reset_pin():
    """Email a single-use Parent PIN recovery link to Parent One."""
    account = get_current_account()
    membership = get_current_membership()
    if account is None or membership is None:
        return redirect(url_for("account.login", next=request.full_path.rstrip("?")))

    if membership["role"] != "owner":
        abort(403)

    if not parent_pin_exists():
        return redirect(url_for("auth.setup_pin"))

    next_url = _safe_next_url(request.args.get("next") or request.form.get("next"))
    recovery_subject = rate_limit_subject(client_ip(), account["id"])

    if request.method == "POST":
        blocked, remaining = rate_limit_is_blocked("parent_pin_recovery", recovery_subject)
        if blocked:
            flash(
                f"Too many recovery requests. Try again in about {max(1, remaining // 60 + 1)} minute(s).",
                "error",
            )
            return render_template(
                "parent/reset_pin.html",
                next_url=next_url or "",
                account=account,
            ), 429

        token = create_pin_reset_token(
            account["id"],
            membership["family_id"],
            requested_ip=client_ip(),
        )
        reset_path = url_for("auth.complete_pin_reset", token=token)
        if next_url:
            reset_path += "?next=" + next_url
        reset_url = application_url(reset_path)

        text_body = (
            f"Hello {account['display_name']},\n\n"
            "A Parent PIN reset was requested for your Family Quest Center family.\n\n"
            f"Reset your Parent PIN: {reset_url}\n\n"
            "This one-time link expires in 30 minutes. "
            "If you did not request it, ignore this message."
        )
        html_body = f"""
            <div style="font-family:Arial,sans-serif;max-width:620px;margin:auto;color:#172033">
              <h1 style="color:#6b3cc4">Family Quest Center</h1>
              <h2>Parent PIN Reset Requested</h2>
              <p>Hello {account['display_name']},</p>
              <p>A Parent PIN reset was requested for your family.</p>
              <p style="margin:30px 0">
                <a href="{reset_url}" style="background:#6b3cc4;color:white;padding:12px 20px;border-radius:8px;text-decoration:none;font-weight:bold">
                  Reset Parent PIN
                </a>
              </p>
              <p>This one-time link expires in 30 minutes. If you did not request it, you can safely ignore this email.</p>
            </div>
        """

        try:
            send_email(
                recipients=account["email"],
                subject="Reset your Family Quest Center Parent PIN",
                text_body=text_body,
                html_body=html_body,
            )
        except (EmailConfigurationError, EmailDeliveryError):
            current_app.logger.warning(
                "Parent PIN recovery email could not be delivered for account id %s",
                account["id"],
            )
            flash(
                "The recovery email could not be sent. Check the email configuration and try again.",
                "error",
            )
        else:
            clear_rate_limit("parent_pin_recovery", recovery_subject)
            log_audit(
                "parent_pin_recovery_requested",
                "parent_account",
                account["id"],
                actor_name=account["display_name"],
            )
            flash(
                "A secure Parent PIN reset link has been sent to your account email.",
                "success",
            )
            return redirect(url_for("auth.login", next=next_url or ""))

    return render_template(
        "parent/reset_pin.html",
        next_url=next_url or "",
        account=account,
    )


@auth_blueprint.route("/reset-pin/<token>", methods=["GET", "POST"])
def complete_pin_reset(token: str):
    """Set a new Parent PIN after a valid one-time email link."""
    reset_request = get_valid_pin_reset(token)
    if reset_request is None:
        flash(
            "That Parent PIN reset link is invalid, expired, or has already been used.",
            "error",
        )
        return redirect(url_for("account.login"))

    next_url = _safe_next_url(request.args.get("next") or request.form.get("next"))

    if request.method == "POST":
        new_pin = request.form.get("new_pin", "").strip()
        confirm_pin = request.form.get("confirm_pin", "").strip()

        if not _valid_four_digit_pin(new_pin):
            flash("The new Parent PIN must contain exactly four digits.", "error")
        elif new_pin != confirm_pin:
            flash("The new Parent PIN entries do not match.", "error")
        else:
            consumed = consume_pin_reset(token)
            if consumed is None:
                flash("That Parent PIN reset link is no longer valid.", "error")
                return redirect(url_for("account.login"))

            account_id, family_id = consumed
            account_row = get_db().execute(
                """SELECT COALESCE(auth_version,0) AS auth_version
                   FROM account_users
                   WHERE id=? AND active=1""",
                (account_id,),
            ).fetchone()
            if account_row is None:
                abort(403)

            session.clear()
            session["account_user_id"] = account_id
            session["family_id"] = family_id
            session["account_role"] = "owner"
            session["auth_version"] = int(account_row["auth_version"] or 0)
            session["parent_authenticated"] = True
            session["parent_last_activity_at"] = int(time.time())
            set_parent_pin_hash(generate_password_hash(new_pin))
            rotate_csrf_token()

            log_audit(
                "parent_pin_reset",
                "parent_account",
                account_id,
                actor_name=reset_request["display_name"],
            )
            flash(
                "Parent PIN reset successfully. Parent access is now unlocked.",
                "success",
            )
            return redirect(next_url or url_for("parent.dashboard"))

    return render_template(
        "parent/complete_pin_reset.html",
        token=token,
        next_url=next_url or "",
    )


@auth_blueprint.route("/login", methods=["GET", "POST"])
def login():
    """Unlock the parent area for the current browser session."""

    if get_current_account() is None or get_current_membership() is None:
        return redirect(url_for("account.login", next=request.full_path.rstrip("?")))

    if not parent_pin_exists():
        return redirect(url_for("auth.setup_pin"))

    next_url = _safe_next_url(request.args.get("next"))

    if request.method == "POST":
        membership = get_current_membership()
        pin_subject = rate_limit_subject(client_ip(), membership["family_id"] if membership else "unknown")
        blocked, remaining = rate_limit_is_blocked("parent_pin_login", pin_subject)
        if blocked:
            flash(f"Too many PIN attempts. Try again in about {max(1, remaining // 60 + 1)} minute(s).", "error")
            return render_template("parent/login.html", next_url=next_url or ""), 429
        pin = request.form.get("pin", "").strip()
        stored_hash = get_parent_pin_hash()

        if stored_hash and check_password_hash(stored_hash, pin):
            session.pop("active_child_id", None)
            session["parent_authenticated"] = True
            session["parent_last_activity_at"] = int(time.time())
            session.permanent = True
            rotate_csrf_token()
            clear_rate_limit("parent_pin_login", pin_subject)
            flash("Parent area unlocked.", "success")
            requested_next = _safe_next_url(request.form.get("next"))
            if requested_next:
                return redirect(requested_next)
            from services.onboarding import family_setup_complete
            return redirect(
                url_for("parent.dashboard")
                if family_setup_complete()
                else url_for("onboarding.family_setup")
            )

        record_rate_limit_failure(
            "parent_pin_login", pin_subject, max_attempts=5, window_seconds=600, block_seconds=600
        )
        flash("Incorrect parent PIN.", "error")

    return render_template(
        "parent/login.html",
        next_url=next_url or "",
    )


@auth_blueprint.route("/logout", methods=["POST"])
def logout():
    """Lock the parent area."""

    session.pop("parent_authenticated", None)
    session.pop("parent_last_activity_at", None)
    session.pop("active_child_id", None)
    session.pop("child_last_activity_at", None)
    flash("Parent area locked.", "success")
    return redirect(url_for("home.family_dashboard"))
