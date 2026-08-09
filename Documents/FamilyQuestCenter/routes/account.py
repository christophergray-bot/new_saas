"""Email/password account authentication and initial family registration."""
from __future__ import annotations

import re
import secrets
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

from flask import abort, Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from database import get_db
from models.administration import log_audit
from models.settings import get_registration_mode, registration_is_enabled, get_setting, set_setting
from services.account_auth import account_required, authenticated_account_required, get_current_account, get_current_membership, is_installation_owner
from services.content_packs import install_pack
from services.email_service import EmailConfigurationError, EmailDeliveryError, send_email
from services.family_security import get_parent_pin_hash, set_parent_pin_hash
from services.account_tokens import (
    application_url,
    consume_password_reset,
    create_password_reset_token,
    ensure_account_token_schema,
    get_valid_password_reset,
)
from services.billing import attach_checkout_to_family
from services.security import (
    clear_rate_limit,
    client_ip,
    rate_limit_is_blocked,
    rate_limit_subject,
    record_rate_limit_failure,
    rotate_csrf_token,
)

account_blueprint = Blueprint("account", __name__, url_prefix="/account")
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def _safe_next(target):
    """Handle the safe next workflow."""
    if not target:
        return None
    host = urlparse(request.host_url)
    candidate = urlparse(urljoin(request.host_url, target))
    return candidate.path if candidate.netloc == host.netloc and candidate.scheme in {"http", "https"} else None


def _valid_password(password: str) -> bool:
    """Handle the valid password workflow."""
    return len(password) >= 10 and any(c.isalpha() for c in password) and any(c.isdigit() for c in password)


def _slug_base(name: str) -> str:
    """Handle the slug base workflow."""
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "family"
    return f"{base}-{secrets.token_hex(3)}"




def _application_owner_exists() -> bool:
    row = get_db().execute(
        "SELECT 1 FROM account_users WHERE platform_role='application_owner' AND active=1 LIMIT 1"
    ).fetchone()
    return row is not None


@account_blueprint.route("/setup-owner", methods=["GET", "POST"])
def setup_owner():
    """Create the one platform-only Application Owner on a fresh install."""
    db = get_db()
    if _application_owner_exists():
        return redirect(url_for("account.login"))
    if db.execute("SELECT COUNT(*) FROM account_users").fetchone()[0] > 0:
        abort(403)
    if request.method == "POST":
        display_name = request.form.get("display_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        if len(display_name) < 2:
            flash("Enter your name.", "error")
        elif not EMAIL_RE.match(email):
            flash("Enter a valid email address.", "error")
        elif password != confirm:
            flash("The password entries do not match.", "error")
        elif not _valid_password(password):
            flash("Use at least 10 characters with a letter and a number.", "error")
        else:
            account_id = db.execute(
                "INSERT INTO account_users(email,password_hash,display_name,email_verified,active,platform_role) VALUES(?,?,?,0,1,'application_owner')",
                (email, generate_password_hash(password), display_name),
            ).lastrowid
            set_setting("installation_owner_account_id", str(account_id))
            db.commit()
            session.clear()
            session["account_user_id"] = account_id
            session["auth_version"] = 0
            session.permanent = True
            rotate_csrf_token()
            flash("Application Owner setup complete.", "success")
            return redirect(url_for("developer.dashboard"))
    return render_template("account/setup_owner.html")

@account_blueprint.route("/register", methods=["GET", "POST"])
def register():
    if not _application_owner_exists():
        return redirect(url_for("account.setup_owner"))
    billing_entitlement = session.get("billing_entitlement")
    stripe_checkout_required = bool(
        current_app.config.get("STRIPE_ENFORCE_SUBSCRIPTIONS")
        or (
            current_app.config.get("PAYMENTS_MODE") in {"test", "live"}
            and current_app.config.get("STRIPE_SECRET_KEY")
            and current_app.config.get("STRIPE_PRICE_ID")
        )
    )
    if stripe_checkout_required and not billing_entitlement:
        flash("Choose the $4.99 monthly membership and complete secure checkout before creating a family account.", "warning")
        return redirect(url_for("billing.plans"))
    if not registration_is_enabled(current_app.config["REGISTRATION_MODE"]):
        flash(
            "New family registration is not currently open. Existing families can still sign in.",
            "warning",
        )
        return render_template("account/registration_closed.html"), 403

    # Registration must remain an explicit public destination. A valid session
    # may exist in another tab, but clicking "Start Your Adventure" must not
    # silently bypass this page and open the Parent Dashboard.
    """Handle the register workflow."""
    existing_account = get_current_account()
    existing_membership = get_current_membership() if existing_account is not None else None
    if request.method == "POST":
        registration_subject = rate_limit_subject(client_ip())
        blocked, remaining = rate_limit_is_blocked("account_register", registration_subject)
        if blocked:
            flash(f"Too many registration attempts. Try again in about {max(1, remaining // 60 + 1)} minute(s).", "error")
            return render_template(
                "account/register.html",
                existing_account=existing_account,
                existing_membership=existing_membership,
                billing_email=(billing_entitlement or {}).get("email", ""),
            ), 429
        family_name = request.form.get("family_name", "").strip()
        display_name = request.form.get("display_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        if billing_entitlement and billing_entitlement.get("email"):
            email = billing_entitlement["email"]
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        starter_experience = request.form.get("starter_experience", "explorer_starter")
        db = get_db()
        if len(family_name) < 2:
            flash("Enter a family name.", "error")
        elif len(display_name) < 2:
            flash("Enter your name.", "error")
        elif not EMAIL_RE.match(email):
            flash("Enter a valid email address.", "error")
        elif password != confirm:
            flash("The password entries do not match.", "error")
        elif not _valid_password(password):
            flash("Use at least 10 characters with a letter and a number.", "error")
        elif starter_experience not in {"explorer_starter", "empty"}:
            flash("Choose a valid starter experience.", "error")
        elif db.execute("SELECT 1 FROM account_users WHERE email=? COLLATE NOCASE", (email,)).fetchone():
            flash("An account already exists for that email address.", "error")
        else:
            try:
                db.execute("BEGIN")
                account_count = db.execute("SELECT COUNT(*) FROM account_users").fetchone()[0]
                if account_count == 0:
                    legacy = db.execute("SELECT id FROM families WHERE slug='default-family' AND status='active'").fetchone()
                else:
                    legacy = None
                if legacy:
                    family_id = legacy["id"]
                    db.execute("UPDATE families SET name=?,updated_at=CURRENT_TIMESTAMP WHERE id=?", (family_name, family_id))
                else:
                    family_id = db.execute(
                        "INSERT INTO families(name,slug,status) VALUES(?,?,'active')",
                        (family_name, _slug_base(family_name)),
                    ).lastrowid
                account_id = db.execute(
                    "INSERT INTO account_users(email,password_hash,display_name,email_verified,active,platform_role) VALUES(?,?,?,0,1,'none')",
                    (email, generate_password_hash(password), display_name),
                ).lastrowid
                db.execute(
                    "INSERT INTO family_memberships(family_id,account_user_id,role,active) VALUES(?,?, 'owner',1)",
                    (family_id, account_id),
                )
                db.commit()
            except Exception:
                db.rollback()
                raise
            session.clear()
            session["account_user_id"] = account_id
            session["family_id"] = family_id
            session["account_role"] = "owner"
            session["auth_version"] = 0
            session.permanent = True
            rotate_csrf_token()
            clear_rate_limit("account_register", registration_subject)
            if billing_entitlement:
                attach_checkout_to_family(billing_entitlement, family_id, account_id)
                session.pop("billing_entitlement", None)

            if starter_experience == "explorer_starter":
                try:
                    counts = install_pack("explorer_starter")
                except Exception:
                    # Account creation must remain successful even if optional
                    # starter content cannot be installed. The parent can install
                    # the pack later from Content Packs.
                    flash(
                        "Your family account is ready, but the Family Quest Starter Pack could not be installed. "
                        "You can install it later from Content Packs.",
                        "warning",
                    )
                else:
                    flash(
                        f"Family Quest Starter Pack added: {counts['quests']} example quest, "
                        f"{counts['adventures']} outdoor adventure, and {counts['books']} Quest Book.",
                        "success",
                    )
            else:
                flash("Your empty family workspace is ready.", "success")

            flash("Create a parent PIN to protect parent tools on shared devices.", "success")
            return redirect(url_for("auth.setup_pin"))
    if request.method == "POST":
        record_rate_limit_failure(
            "account_register", registration_subject, max_attempts=10, window_seconds=3600, block_seconds=1800
        )
    return render_template(
        "account/register.html",
        existing_account=existing_account,
        existing_membership=existing_membership,
        billing_email=(billing_entitlement or {}).get("email", ""),
    )


@account_blueprint.route("/login", methods=["GET", "POST"])
def login():
    # Sign In is always an explicit page. Do not redirect an existing browser
    # session straight to the Parent Dashboard; users may be switching families
    # or verifying which account is active. A successful POST replaces the
    # complete session below.
    """Handle the login workflow."""
    existing_account = get_current_account()
    existing_membership = get_current_membership() if existing_account is not None else None
    next_url = _safe_next(request.args.get("next"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        login_subject = rate_limit_subject(client_ip(), email)
        blocked, remaining = rate_limit_is_blocked("account_login", login_subject)
        if blocked:
            flash(f"Too many sign-in attempts. Try again in about {max(1, remaining // 60 + 1)} minute(s).", "error")
            return render_template(
                "account/login.html",
                next_url=next_url or "",
                existing_account=existing_account,
                existing_membership=existing_membership,
            ), 429
        password = request.form.get("password", "")
        remember = request.form.get("remember") == "1"
        db = get_db()
        row = db.execute(
            "SELECT id,email,password_hash,display_name,active,COALESCE(auth_version,0) AS auth_version,COALESCE(platform_role, 'none') AS platform_role FROM account_users WHERE email=? COLLATE NOCASE",
            (email,),
        ).fetchone()
        password_valid = bool(
            row
            and row["active"]
            and check_password_hash(row["password_hash"], password)
        )
        membership = None
        if password_valid:
            membership = db.execute(
                """SELECT fm.family_id,fm.role FROM family_memberships fm JOIN families f ON f.id=fm.family_id
                   WHERE fm.account_user_id=? AND fm.active=1 AND f.status='active' ORDER BY fm.id LIMIT 1""",
                (row["id"],),
            ).fetchone()

        # FC-0020 diagnostic logging: records only boolean outcomes and lengths.
        # Never log the submitted email address, password, hash, or session token.
        current_app.logger.warning(
            "FC-0020 login diagnostic: remember=%s email_length=%s password_length=%s "
            "account_found=%s account_active=%s password_valid=%s platform_owner=%s membership_found=%s",
            remember,
            len(email),
            len(password),
            row is not None,
            bool(row and row["active"]),
            password_valid,
            bool(row and row["platform_role"] == "application_owner"),
            membership is not None,
        )

        if password_valid and row["platform_role"] == "application_owner":
            session.clear()
            session["account_user_id"] = row["id"]
            session["auth_version"] = int(row["auth_version"] or 0)
            session.permanent = remember
            rotate_csrf_token()
            clear_rate_limit("account_login", login_subject)
            db.execute(
                "UPDATE account_users SET last_login_at=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (datetime.now(timezone.utc).isoformat(timespec="seconds"), row["id"]),
            )
            db.commit()
            flash(f"Welcome back, {row['display_name']}.", "success")
            return redirect(url_for("developer.dashboard"))
        if membership:
            session.clear()
            session["account_user_id"] = row["id"]
            session["family_id"] = membership["family_id"]
            session["account_role"] = membership["role"]
            session["auth_version"] = int(row["auth_version"] or 0)
            session.permanent = remember
            rotate_csrf_token()
            clear_rate_limit("account_login", login_subject)
            db.execute(
                "UPDATE account_users SET last_login_at=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (datetime.now(timezone.utc).isoformat(timespec="seconds"), row["id"]),
            )
            db.commit()
            flash(f"Welcome back, {row['display_name']}.", "success")
            return redirect(_safe_next(request.form.get("next")) or url_for("parent.dashboard"))
        record_rate_limit_failure(
            "account_login", login_subject, max_attempts=5, window_seconds=900, block_seconds=900
        )
        flash("The email or password was not recognized.", "error")
    return render_template(
        "account/login.html",
        next_url=next_url or "",
        existing_account=existing_account,
        existing_membership=existing_membership,
    )


@account_blueprint.route("/logout", methods=["POST"])
def logout():
    """Handle the logout workflow."""
    session.clear()
    flash("You have been signed out.", "success")
    return redirect(url_for("account.login"))


@account_blueprint.route("/profile", methods=["GET", "POST"])
@authenticated_account_required
def profile():
    """Review the signed-in parent account and manage parent-specific security."""
    account = get_current_account()
    membership = get_current_membership()
    if request.method == "POST" and request.form.get("form_action") in {"change_pin", "reset_pin"}:
        # The shared family PIN is an owner-controlled security setting.
        if membership is None or membership["role"] != "owner":
            abort(403)

    if request.method == "POST" and request.form.get("form_action") == "change_pin":
        pin_subject = rate_limit_subject(client_ip(), account["id"])
        blocked, remaining = rate_limit_is_blocked("parent_pin_change", pin_subject)
        if blocked:
            flash(f"Too many PIN attempts. Try again in about {max(1, remaining // 60 + 1)} minute(s).", "error")
            return render_template("account/profile.html", account=account, membership=membership), 429

        current_pin = request.form.get("current_pin", "").strip()
        new_pin = request.form.get("new_pin", "").strip()
        confirm_pin = request.form.get("confirm_pin", "").strip()
        stored_hash = get_parent_pin_hash()

        if not stored_hash or not check_password_hash(stored_hash, current_pin):
            record_rate_limit_failure("parent_pin_change", pin_subject, max_attempts=5, window_seconds=900, block_seconds=900)
            flash("The current Parent PIN is incorrect.", "error")
        elif len(new_pin) != 4 or not new_pin.isdigit():
            flash("The new Parent PIN must contain exactly four digits.", "error")
        elif new_pin != confirm_pin:
            flash("The new Parent PIN entries do not match.", "error")
        elif new_pin == current_pin:
            flash("Choose a different Parent PIN.", "warning")
        else:
            set_parent_pin_hash(generate_password_hash(new_pin))
            session["parent_authenticated"] = True
            clear_rate_limit("parent_pin_change", pin_subject)
            log_audit("parent_pin_changed", "parent_account", account["id"], actor_name=account["display_name"])
            flash("Parent PIN changed successfully.", "success")
            return redirect(url_for("account.profile") + "#security")

    if request.method == "POST" and request.form.get("form_action") == "reset_pin":
        pin_subject = rate_limit_subject(client_ip(), account["id"])
        blocked, remaining = rate_limit_is_blocked("parent_pin_reset", pin_subject)
        if blocked:
            flash(f"Too many reset attempts. Try again in about {max(1, remaining // 60 + 1)} minute(s).", "error")
            return render_template("account/profile.html", account=account, membership=membership), 429

        account_password = request.form.get("account_password", "")
        new_pin = request.form.get("reset_new_pin", "").strip()
        confirm_pin = request.form.get("reset_confirm_pin", "").strip()
        db = get_db()
        password_row = db.execute(
            "SELECT password_hash FROM account_users WHERE id=? AND active=1",
            (account["id"],),
        ).fetchone()

        if not password_row or not check_password_hash(password_row["password_hash"], account_password):
            record_rate_limit_failure(
                "parent_pin_reset", pin_subject, max_attempts=5, window_seconds=900, block_seconds=900
            )
            flash("The account password was incorrect.", "error")
        elif len(new_pin) != 4 or not new_pin.isdigit():
            flash("The new Parent PIN must contain exactly four digits.", "error")
        elif new_pin != confirm_pin:
            flash("The new Parent PIN entries do not match.", "error")
        else:
            set_parent_pin_hash(generate_password_hash(new_pin))
            session["parent_authenticated"] = True
            rotate_csrf_token()
            clear_rate_limit("parent_pin_reset", pin_subject)
            log_audit("parent_pin_reset", "parent_account", account["id"], actor_name=account["display_name"])
            flash("Parent PIN reset successfully using your account password.", "success")
            return redirect(url_for("account.profile") + "#security")

    return render_template("account/profile.html", account=account, membership=membership)


@account_blueprint.route("/change-password", methods=["GET", "POST"])
@account_required
def change_password():
    """Handle the change password workflow."""
    account = get_current_account()
    if request.method == "POST":
        password_subject = rate_limit_subject(client_ip(), account["id"])
        blocked, remaining = rate_limit_is_blocked("change_password", password_subject)
        if blocked:
            flash(f"Too many password attempts. Try again in about {max(1, remaining // 60 + 1)} minute(s).", "error")
            return render_template("account/change_password.html"), 429
        current = request.form.get("current_password", "")
        new = request.form.get("new_password", "")
        confirm = request.form.get("confirm_password", "")
        starter_experience = request.form.get("starter_experience", "explorer_starter")
        db = get_db()
        row = db.execute("SELECT password_hash FROM account_users WHERE id=?", (account["id"],)).fetchone()
        if not check_password_hash(row["password_hash"], current):
            record_rate_limit_failure(
                "change_password", password_subject, max_attempts=5, window_seconds=900, block_seconds=900
            )
            flash("Your current password was incorrect.", "error")
        elif new != confirm:
            flash("The new password entries do not match.", "error")
        elif not _valid_password(new):
            flash("Use at least 10 characters with a letter and a number.", "error")
        else:
            db.execute("UPDATE account_users SET password_hash=?,auth_version=auth_version+1,updated_at=CURRENT_TIMESTAMP WHERE id=?", (generate_password_hash(new), account["id"]))
            db.commit()
            clear_rate_limit("change_password", password_subject)
            session.clear()
            flash("Password changed successfully. Sign in again with your new password.", "success")
            return redirect(url_for("account.login"))
    return render_template("account/change_password.html")


@account_blueprint.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    """Send a non-enumerating password recovery response."""
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        subject_key = rate_limit_subject(client_ip(), email)
        blocked, remaining = rate_limit_is_blocked("forgot_password", subject_key)
        if blocked:
            flash(
                f"Too many recovery requests. Try again in about {max(1, remaining // 60 + 1)} minute(s).",
                "error",
            )
            return render_template("account/forgot_password.html"), 429

        ensure_account_token_schema()
        account = get_db().execute(
            "SELECT id,email,display_name FROM account_users WHERE email=? COLLATE NOCASE AND active=1",
            (email,),
        ).fetchone()
        if account is not None:
            token = create_password_reset_token(account["id"], requested_ip=client_ip())
            reset_url = application_url(url_for("account.reset_password", token=token))
            text_body = (
                f"Hello {account['display_name']},\n\n"
                "A password reset was requested for your Family Quest Center account.\n\n"
                f"Reset your password: {reset_url}\n\n"
                "This one-time link expires in 60 minutes. If you did not request it, ignore this message."
            )
            html_body = f"""
                <div style="font-family:Arial,sans-serif;max-width:620px;margin:auto;color:#172033">
                  <h1 style="color:#6b3cc4">Family Quest Center</h1>
                  <h2>Password Reset Requested</h2>
                  <p>Hello {account['display_name']},</p>
                  <p>A password reset was requested for your parent account.</p>
                  <p style="margin:30px 0"><a href="{reset_url}" style="background:#6b3cc4;color:white;padding:12px 20px;border-radius:8px;text-decoration:none;font-weight:bold">Reset My Password</a></p>
                  <p>This one-time link expires in 60 minutes. If you did not request it, you can safely ignore this email.</p>
                </div>
            """
            try:
                send_email(
                    recipients=account["email"],
                    subject="Reset your Family Quest Center password",
                    text_body=text_body,
                    html_body=html_body,
                )
            except (EmailConfigurationError, EmailDeliveryError):
                current_app.logger.warning("Password reset email could not be delivered for account id %s", account["id"])
            else:
                log_audit("password_reset_requested", "parent_account", account["id"], actor_name=account["display_name"])

        record_rate_limit_failure(
            "forgot_password", subject_key, max_attempts=5, window_seconds=3600, block_seconds=3600
        )
        flash("If an active account matches that email, password reset instructions have been sent.", "success")
        return redirect(url_for("account.login"))
    return render_template("account/forgot_password.html")


@account_blueprint.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token: str):
    """Validate and consume a one-time password reset token."""
    reset_account = get_valid_password_reset(token)
    if reset_account is None:
        flash("That password reset link is invalid, expired, or has already been used.", "error")
        return redirect(url_for("account.forgot_password"))

    if request.method == "POST":
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        if password != confirm:
            flash("The password entries do not match.", "error")
        elif not _valid_password(password):
            flash("Use at least 10 characters with a letter and a number.", "error")
        else:
            account_id = consume_password_reset(token, generate_password_hash(password))
            if account_id is None:
                flash("That password reset link is no longer valid.", "error")
                return redirect(url_for("account.forgot_password"))
            session.clear()
            rotate_csrf_token()
            log_audit("account_password_reset", "parent_account", account_id, actor_name=reset_account["display_name"])
            flash("Your password has been reset. Sign in with your new password.", "success")
            return redirect(url_for("account.login"))
    return render_template("account/reset_password.html", reset_account=reset_account)
