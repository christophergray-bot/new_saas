"""Parent account management for Parent One and Parent Two."""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from database import get_db
from models.administration import log_audit
from models.settings import get_bool_setting, get_public_settings, get_setting, set_settings
from services.account_auth import get_current_account, get_current_membership
from services.account_tokens import application_url, ensure_account_token_schema, hash_invitation_token
from services.email_service import EmailConfigurationError, EmailDeliveryError, send_email
from services.security import rotate_csrf_token

parent_management_blueprint = Blueprint(
    "parent_management", __name__, url_prefix="/parent/management"
)


def _has_usable_password_hash(value: str | None) -> bool:
    """Return whether an account has a real Werkzeug password hash.

    Older Parent Two workflows could leave a placeholder account record before
    the invited parent had chosen a password. Those records must follow the
    first-time setup branch rather than being told to sign in.
    """
    password_hash = str(value or "").strip().lower()
    return password_hash.startswith(("scrypt:", "pbkdf2:", "argon2:"))


def _ensure_tables() -> None:
    """Handle the ensure tables workflow."""
    db = get_db()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS parent_invitations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            family_id INTEGER NOT NULL,
            email TEXT NOT NULL COLLATE NOCASE,
            role TEXT NOT NULL DEFAULT 'parent' CHECK(role='parent'),
            token TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','accepted','cancelled')),
            invited_by_account_id INTEGER,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            accepted_at TEXT,
            token_hash TEXT,
            expires_at TEXT,
            FOREIGN KEY(family_id) REFERENCES families(id),
            FOREIGN KEY(invited_by_account_id) REFERENCES account_users(id)
        );
        """
    )
    columns = {row["name"] for row in db.execute("PRAGMA table_info(parent_invitations)").fetchall()}
    if "token_hash" not in columns:
        db.execute("ALTER TABLE parent_invitations ADD COLUMN token_hash TEXT")
    if "expires_at" not in columns:
        db.execute("ALTER TABLE parent_invitations ADD COLUMN expires_at TEXT")

    # Earlier versions used UNIQUE(family_id, email, status). That prevented a
    # second cancellation for the same address and caused hosted invitation
    # management to fail. Rebuild the table once without that legacy rule,
    # then enforce uniqueness only for currently pending invitations.
    table_sql_row = db.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='parent_invitations'"
    ).fetchone()
    table_sql = str(table_sql_row["sql"] or "") if table_sql_row else ""
    normalized_sql = "".join(table_sql.lower().split())
    if "unique(family_id,email,status)" in normalized_sql:
        db.executescript(
            """
            ALTER TABLE parent_invitations RENAME TO parent_invitations_legacy;
            CREATE TABLE parent_invitations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                family_id INTEGER NOT NULL,
                email TEXT NOT NULL COLLATE NOCASE,
                role TEXT NOT NULL DEFAULT 'parent' CHECK(role='parent'),
                token TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','accepted','cancelled')),
                invited_by_account_id INTEGER,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                accepted_at TEXT,
                token_hash TEXT,
                expires_at TEXT,
                FOREIGN KEY(family_id) REFERENCES families(id),
                FOREIGN KEY(invited_by_account_id) REFERENCES account_users(id)
            );
            INSERT INTO parent_invitations
                (id,family_id,email,role,token,status,invited_by_account_id,
                 created_at,accepted_at,token_hash,expires_at)
            SELECT id,family_id,email,role,token,status,invited_by_account_id,
                   created_at,accepted_at,token_hash,expires_at
            FROM parent_invitations_legacy;
            DROP TABLE parent_invitations_legacy;
            """
        )

    db.execute(
        """CREATE UNIQUE INDEX IF NOT EXISTS uq_parent_invitation_pending
           ON parent_invitations(family_id, email)
           WHERE status='pending'"""
    )
    db.commit()


def _family_id() -> int:
    """Handle the family id workflow."""
    membership = get_current_membership()
    if membership is None:
        abort(403)
    return int(membership["family_id"])


def _parents():
    """Handle the parents workflow."""
    return get_db().execute(
        """SELECT au.id, au.email, au.display_name, au.last_login_at, au.created_at,
                  fm.role, fm.active
           FROM family_memberships fm
           JOIN account_users au ON au.id=fm.account_user_id
           WHERE fm.family_id=? AND fm.active=1 AND fm.role IN ('owner','parent')
           ORDER BY CASE fm.role WHEN 'owner' THEN 0 ELSE 1 END, fm.created_at""",
        (_family_id(),),
    ).fetchall()


@parent_management_blueprint.route("/")
def overview():
    """Handle the overview workflow."""
    _ensure_tables()
    parents = _parents()
    invitation = get_db().execute(
        """SELECT id,email,status,created_at,expires_at FROM parent_invitations
           WHERE family_id=? AND status='pending' ORDER BY id DESC LIMIT 1""",
        (_family_id(),),
    ).fetchone()
    return render_template(
        "parent_management/overview.html",
        parents=parents,
        invitation=invitation,
        membership=get_current_membership(),
    )


@parent_management_blueprint.route("/invite", methods=["POST"])
def invite_parent_two():
    """Handle the invite parent two workflow."""
    _ensure_tables()
    membership = get_current_membership()
    if membership["role"] != "owner":
        abort(403)
    if len(_parents()) >= 2:
        flash("Parent Two is already assigned.", "warning")
        return redirect(url_for("parent_management.overview"))
    email = request.form.get("email", "").strip().lower()
    if "@" not in email or "." not in email.rsplit("@", 1)[-1]:
        flash("Enter a valid email address.", "error")
        return redirect(url_for("parent_management.overview"))
    db = get_db()
    existing = db.execute("SELECT id FROM account_users WHERE email=? COLLATE NOCASE", (email,)).fetchone()
    if existing:
        family_membership = db.execute(
            "SELECT 1 FROM family_memberships WHERE family_id=? AND account_user_id=? AND active=1",
            (_family_id(), existing["id"]),
        ).fetchone()
        if family_membership:
            flash("That account is already part of this family.", "warning")
            return redirect(url_for("parent_management.overview"))
    db.execute(
        "UPDATE parent_invitations SET status='cancelled' WHERE family_id=? AND status='pending'",
        (_family_id(),),
    )
    raw_token = secrets.token_urlsafe(32)
    token_hash = hash_invitation_token(raw_token)
    expires_at = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(timespec="seconds")
    # The legacy token column remains populated with a hash so existing hosted
    # databases keep their NOT NULL constraint without storing the raw token.
    db.execute(
        """INSERT INTO parent_invitations
           (family_id,email,token,token_hash,expires_at,invited_by_account_id)
           VALUES (?,?,?,?,?,?)""",
        (_family_id(), email, token_hash, token_hash, expires_at, get_current_account()["id"]),
    )
    db.commit()
    family = db.execute("SELECT name FROM families WHERE id=?", (_family_id(),)).fetchone()
    invite_url = application_url(url_for("parent_management.accept_invitation", token=raw_token))
    inviter = get_current_account()["display_name"]
    text_body = (
        f"{inviter} invited you to join {family['name']} in Family Quest Center as Parent Two.\n\n"
        f"Accept the invitation: {invite_url}\n\nThis one-time invitation expires in 7 days."
    )
    html_body = f"""
      <div style="font-family:Arial,sans-serif;max-width:620px;margin:auto;color:#172033">
        <h1 style="color:#6b3cc4">Family Quest Center</h1>
        <h2>You're Invited as Parent Two</h2>
        <p><strong>{inviter}</strong> invited you to join <strong>{family['name']}</strong>.</p>
        <p style="margin:30px 0"><a href="{invite_url}" style="background:#6b3cc4;color:white;padding:12px 20px;border-radius:8px;text-decoration:none;font-weight:bold">Accept Parent Invitation</a></p>
        <p>This one-time invitation expires in 7 days.</p>
      </div>
    """
    try:
        send_email(recipients=email, subject=f"Join {family['name']} in Family Quest Center", text_body=text_body, html_body=html_body)
    except (EmailConfigurationError, EmailDeliveryError):
        db.execute("UPDATE parent_invitations SET status='cancelled' WHERE family_id=? AND token_hash=?", (_family_id(), token_hash))
        db.commit()
        flash("The invitation email could not be sent. Verify hosted email and try again.", "error")
        return redirect(url_for("parent_management.overview"))
    log_audit("parent_two_invited", "parent_account", details=f"Invitation sent to {email}", actor_name=inviter)
    flash("Parent Two invitation email sent.", "success")
    return redirect(url_for("parent_management.overview"))


@parent_management_blueprint.route("/invitation/<token>", methods=["GET", "POST"])
def accept_invitation(token: str):
    """Allow the invited email address to create or confirm its parent account."""
    _ensure_tables()
    ensure_account_token_schema()
    db = get_db()
    invitation = db.execute(
        """SELECT pi.id,pi.family_id,pi.email,pi.expires_at,pi.status,f.name AS family_name
           FROM parent_invitations pi JOIN families f ON f.id=pi.family_id
           WHERE pi.token_hash=? AND pi.status='pending'""",
        (hash_invitation_token(token),),
    ).fetchone()
    valid = invitation is not None
    if valid:
        try:
            expiry = datetime.fromisoformat(invitation["expires_at"])
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)
            valid = expiry > datetime.now(timezone.utc)
        except (TypeError, ValueError):
            valid = False
    if not valid:
        flash("That parent invitation is invalid, expired, or no longer available.", "error")
        return redirect(url_for("account.login"))

    existing = db.execute(
        "SELECT id,email,password_hash,display_name,active FROM account_users WHERE email=? COLLATE NOCASE",
        (invitation["email"],),
    ).fetchone()
    existing_membership = None
    if existing:
        existing_membership = db.execute(
            "SELECT 1 FROM family_memberships WHERE account_user_id=? AND active=1 LIMIT 1",
            (existing["id"],),
        ).fetchone()
    # A real existing user must have both a recognized password hash and an
    # active family membership. Orphaned placeholder rows from older invite
    # attempts are treated as first-time setup accounts.
    existing_has_password = bool(
        existing
        and existing_membership
        and _has_usable_password_hash(existing["password_hash"])
    )

    if request.method == "POST":
        password = request.form.get("password", "")
        if existing_has_password:
            if not existing["active"] or not check_password_hash(existing["password_hash"], password):
                flash("The password for that existing account was not recognized.", "error")
                return render_template(
                    "parent_management/accept_invitation.html",
                    invitation=invitation,
                    existing_account=existing,
                    account_needs_setup=False,
                )
            account_id = existing["id"]
            display_name = existing["display_name"]
        else:
            display_name = request.form.get("display_name", "").strip()
            confirm = request.form.get("confirm_password", "")
            if len(display_name) < 2:
                flash("Enter your name.", "error")
                return render_template(
                    "parent_management/accept_invitation.html",
                    invitation=invitation,
                    existing_account=None,
                    account_needs_setup=True,
                )
            if password != confirm:
                flash("The password entries do not match.", "error")
                return render_template(
                    "parent_management/accept_invitation.html",
                    invitation=invitation,
                    existing_account=None,
                    account_needs_setup=True,
                )
            if len(password) < 10 or not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
                flash("Use at least 10 characters with a letter and a number.", "error")
                return render_template(
                    "parent_management/accept_invitation.html",
                    invitation=invitation,
                    existing_account=None,
                    account_needs_setup=True,
                )

            new_hash = generate_password_hash(password)
            if existing:
                account_id = existing["id"]
                db.execute(
                    """UPDATE account_users
                       SET password_hash=?, display_name=?, email_verified=1, active=1,
                           auth_version=auth_version+1, updated_at=CURRENT_TIMESTAMP
                       WHERE id=?""",
                    (new_hash, display_name, account_id),
                )
            else:
                account_id = db.execute(
                    "INSERT INTO account_users(email,password_hash,display_name,email_verified,active) VALUES(?,?,?,1,1)",
                    (invitation["email"], new_hash, display_name),
                ).lastrowid

        membership = db.execute(
            "SELECT id,active FROM family_memberships WHERE family_id=? AND account_user_id=?",
            (invitation["family_id"], account_id),
        ).fetchone()
        if membership:
            db.execute("UPDATE family_memberships SET role='parent',active=1 WHERE id=?", (membership["id"],))
        else:
            db.execute(
                "INSERT INTO family_memberships(family_id,account_user_id,role,active) VALUES(?,?, 'parent',1)",
                (invitation["family_id"], account_id),
            )
        db.execute(
            "UPDATE parent_invitations SET status='accepted',accepted_at=CURRENT_TIMESTAMP WHERE id=? AND status='pending'",
            (invitation["id"],),
        )
        db.commit()
        session.clear()
        session["account_user_id"] = account_id
        session["family_id"] = invitation["family_id"]
        session["account_role"] = "parent"
        version_row = db.execute("SELECT auth_version FROM account_users WHERE id=?", (account_id,)).fetchone()
        session["auth_version"] = int(version_row["auth_version"] or 0)
        session.permanent = True
        rotate_csrf_token()
        log_audit("parent_two_invitation_accepted", "parent_account", account_id, details=invitation["email"], actor_name=display_name)
        flash(
            "Invitation accepted. Your parent password is ready. Enter the shared Family PIN to unlock the parent area.",
            "success",
        )
        return redirect(url_for("auth.login", next=url_for("parent.dashboard")))
    return render_template(
        "parent_management/accept_invitation.html",
        invitation=invitation,
        existing_account=existing if existing_has_password else None,
        account_needs_setup=not existing_has_password,
    )


@parent_management_blueprint.route("/invitation/resend", methods=["POST"])
def resend_invitation():
    """Replace the pending Parent Two invitation with a fresh one-time link."""
    _ensure_tables()
    membership = get_current_membership()
    if membership is None or membership["role"] != "owner":
        abort(403)

    db = get_db()
    pending = db.execute(
        """SELECT id,email FROM parent_invitations
           WHERE family_id=? AND status='pending' ORDER BY id DESC LIMIT 1""",
        (_family_id(),),
    ).fetchone()
    if pending is None:
        flash("There is no pending Parent Two invitation to resend.", "warning")
        return redirect(url_for("parent_management.overview"))

    raw_token = secrets.token_urlsafe(32)
    token_hash = hash_invitation_token(raw_token)
    expires_at = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(timespec="seconds")

    # Invalidate the previous link before issuing the replacement.
    db.execute(
        "UPDATE parent_invitations SET status='cancelled' WHERE id=? AND status='pending'",
        (pending["id"],),
    )
    invitation_id = db.execute(
        """INSERT INTO parent_invitations
           (family_id,email,token,token_hash,expires_at,invited_by_account_id)
           VALUES (?,?,?,?,?,?)""",
        (_family_id(), pending["email"], token_hash, token_hash, expires_at, get_current_account()["id"]),
    ).lastrowid
    db.commit()

    family = db.execute("SELECT name FROM families WHERE id=?", (_family_id(),)).fetchone()
    inviter = get_current_account()["display_name"]
    invite_url = application_url(url_for("parent_management.accept_invitation", token=raw_token))
    text_body = (
        f"{inviter} resent your invitation to join {family['name']} in Family Quest Center as Parent Two.\n\n"
        f"Accept the invitation: {invite_url}\n\nThis one-time invitation expires in 7 days."
    )
    html_body = f"""
      <div style="font-family:Arial,sans-serif;max-width:620px;margin:auto;color:#172033">
        <h1 style="color:#6b3cc4">Family Quest Center</h1>
        <h2>Your Parent Two Invitation</h2>
        <p><strong>{inviter}</strong> invited you to join <strong>{family['name']}</strong>.</p>
        <p style="margin:30px 0"><a href="{invite_url}" style="background:#6b3cc4;color:white;padding:12px 20px;border-radius:8px;text-decoration:none;font-weight:bold">Accept Parent Invitation</a></p>
        <p>This replacement link expires in 7 days. Any earlier invitation link is no longer valid.</p>
      </div>
    """
    try:
        send_email(
            recipients=pending["email"],
            subject=f"Join {family['name']} in Family Quest Center",
            text_body=text_body,
            html_body=html_body,
        )
    except (EmailConfigurationError, EmailDeliveryError):
        db.execute("UPDATE parent_invitations SET status='cancelled' WHERE id=?", (invitation_id,))
        db.commit()
        flash("The replacement invitation email could not be sent. Verify hosted email and try again.", "error")
        return redirect(url_for("parent_management.overview"))

    log_audit(
        "parent_two_invitation_resent",
        "parent_account",
        details=f"Invitation resent to {pending['email']}",
        actor_name=inviter,
    )
    flash("Parent Two invitation resent. The earlier link has been disabled.", "success")
    return redirect(url_for("parent_management.overview"))


@parent_management_blueprint.route("/invitation/cancel", methods=["POST"])
def cancel_invitation():
    """Handle the cancel invitation workflow."""
    if get_current_membership()["role"] != "owner":
        abort(403)
    get_db().execute(
        "UPDATE parent_invitations SET status='cancelled' WHERE family_id=? AND status='pending'",
        (_family_id(),),
    )
    get_db().commit()
    log_audit("parent_two_invitation_cancelled", "parent_account", actor_name=get_current_account()["display_name"])
    flash("Parent Two invitation cancelled.", "success")
    return redirect(url_for("parent_management.overview"))


@parent_management_blueprint.route("/remove/<int:account_id>", methods=["POST"])
def remove_parent_two(account_id: int):
    """Handle the remove parent two workflow."""
    membership = get_current_membership()
    if membership["role"] != "owner":
        abort(403)
    row = get_db().execute(
        """SELECT fm.id, fm.role, au.display_name FROM family_memberships fm
           JOIN account_users au ON au.id=fm.account_user_id
           WHERE fm.family_id=? AND fm.account_user_id=? AND fm.active=1""",
        (_family_id(), account_id),
    ).fetchone()
    if row is None or row["role"] != "parent":
        abort(404)
    db = get_db()
    db.execute("UPDATE family_memberships SET active=0 WHERE id=?", (row["id"],))
    # Invalidate Parent Two's active sessions immediately. Their account and
    # historical activity remain intact, and other family memberships are not changed.
    db.execute(
        "UPDATE account_users SET auth_version=auth_version+1, updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (account_id,),
    )
    db.commit()
    log_audit("parent_two_removed", "parent_account", account_id, details=row["display_name"], actor_name=get_current_account()["display_name"])
    flash("Parent Two has been removed from the family.", "success")
    return redirect(url_for("parent_management.overview"))


@parent_management_blueprint.route("/security")
def security():
    """Preserve the legacy security URL and direct parents to My Profile."""
    return redirect(url_for("account.profile") + "#security")


@parent_management_blueprint.route("/notifications", methods=["GET", "POST"])
def notifications():
    """Handle the notifications workflow."""
    keys = {
        "notify_weekly_summary": True,
        "notify_reward_approvals": True,
        "notify_adventure_completion": True,
        "notify_system": True,
    }
    if request.method == "POST":
        set_settings({key: "1" if request.form.get(key) == "on" else "0" for key in keys})
        log_audit("parent_notification_preferences_updated", "parent_account", actor_name=get_current_account()["display_name"])
        flash("Notification preferences saved.", "success")
        return redirect(url_for("parent_management.notifications"))
    preferences = {key: get_bool_setting(key, default) for key, default in keys.items()}
    return render_template("parent_management/notifications.html", preferences=preferences)


@parent_management_blueprint.route("/activity")
def activity():
    """Show recent parent activity for the authenticated family only."""
    db = get_db()
    columns = {row["name"] for row in db.execute("PRAGMA table_info(audit_log)").fetchall()}
    if "family_id" not in columns:
        db.execute("ALTER TABLE audit_log ADD COLUMN family_id INTEGER")
        db.execute("CREATE INDEX IF NOT EXISTS audit_log_family_index ON audit_log(family_id, created_at DESC)")
        db.commit()
    rows = db.execute(
        """SELECT action, actor_name, details, created_at FROM audit_log
           WHERE family_id=?
             AND (action LIKE 'parent_%'
                  OR action IN ('account_password_changed','account_profile_updated'))
           ORDER BY id DESC LIMIT 50""",
        (_family_id(),),
    ).fetchall()
    return render_template("parent_management/activity.html", activity=rows)


@parent_management_blueprint.route("/family-settings", methods=["GET", "POST"])
def family_settings():
    """Manage settings that apply to the entire family workspace."""
    family_id = _family_id()
    db = get_db()
    family = db.execute("SELECT id,name FROM families WHERE id=?", (family_id,)).fetchone()

    if request.method == "POST":
        form_action = request.form.get("form_action", "identity")
        errors = []

        if form_action == "identity":
            application_name = request.form.get("application_name", "").strip()
            family_name = request.form.get("family_name", "").strip()
            timezone_name = request.form.get("timezone", "America/Los_Angeles").strip()
            country = request.form.get("country", "United States").strip()
            date_format = request.form.get("date_format", "MM/DD/YYYY").strip()
            if not application_name or len(application_name) > 60:
                errors.append("Application name must be between 1 and 60 characters.")
            if len(family_name) < 2 or len(family_name) > 60:
                errors.append("Family name must be between 2 and 60 characters.")
            if not errors:
                db.execute("UPDATE families SET name=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (family_name, family_id))
                db.commit()
                set_settings({
                    "application_name": application_name,
                    "family_name": family_name,
                    "family_timezone": timezone_name,
                    "family_country": country,
                    "family_date_format": date_format,
                })
                log_audit("family_identity_updated", "family", family_id, actor_name=get_current_account()["display_name"])
                flash("Family identity saved.", "success")
                return redirect(url_for("parent_management.family_settings") + "#identity")

        elif form_action == "quest_defaults":
            try:
                difficulty = int(request.form.get("default_quest_difficulty", "1"))
                stars = int(request.form.get("default_quest_stars", "1"))
            except ValueError:
                errors.append("Quest defaults must contain whole numbers.")
            else:
                if difficulty not in range(1, 6):
                    errors.append("Default difficulty must be between 1 and 5.")
                if stars < 0 or stars > 1000:
                    errors.append("Default stars must be between 0 and 1,000.")
            if not errors:
                set_settings({
                    "default_quest_difficulty": str(difficulty),
                    "default_quest_stars": str(stars),
                    "default_approval_required": "1" if request.form.get("default_approval_required") == "on" else "0",
                })
                log_audit("quest_defaults_updated", "settings", actor_name=get_current_account()["display_name"])
                flash("Quest defaults saved.", "success")
                return redirect(url_for("parent_management.family_settings") + "#quest-defaults")

        elif form_action == "operations":
            daily_reset_time = request.form.get("daily_reset_time", "04:00").strip()
            try:
                grace_days = int(request.form.get("streak_grace_days", "3"))
            except ValueError:
                errors.append("Streak grace days must be a whole number.")
            else:
                if grace_days < 0 or grace_days > 7:
                    errors.append("Streak grace days must be between 0 and 7.")
            if len(daily_reset_time) != 5 or daily_reset_time[2] != ":":
                errors.append("Daily reset time must use HH:MM format.")
            if not errors:
                set_settings({"daily_reset_time": daily_reset_time, "streak_grace_days": str(grace_days)})
                log_audit("family_operations_updated", "settings", actor_name=get_current_account()["display_name"])
                flash("Operations settings saved.", "success")
                return redirect(url_for("parent_management.family_settings") + "#operations")

        elif form_action == "experience":
            xp_values = {}
            defaults = {1: 10, 2: 20, 3: 35, 4: 50, 5: 75}
            for level in range(1, 6):
                field_name = f"xp_difficulty_{level}"
                try:
                    value = int(request.form.get(field_name, defaults[level]))
                except (TypeError, ValueError):
                    errors.append(f"Difficulty {level} XP must be a whole number.")
                    continue
                if value < 0 or value > 10000:
                    errors.append(f"Difficulty {level} XP must be between 0 and 10,000.")
                xp_values[field_name] = str(value)
            if not errors:
                set_settings(xp_values)
                log_audit("experience_settings_updated", "settings", actor_name=get_current_account()["display_name"])
                flash("Experience and progression settings saved.", "success")
                return redirect(url_for("parent_management.family_settings") + "#experience")

        elif form_action == "session":
            try:
                timeout = int(request.form.get("session_timeout_seconds", "600"))
                child_timeout = int(request.form.get("child_session_timeout_seconds", "43200"))
            except ValueError:
                errors.append("Session timeouts must be whole numbers.")
            else:
                if timeout < 60 or timeout > 86400:
                    errors.append("Parent session timeout must be between 60 and 86,400 seconds.")
                if child_timeout < 3600 or child_timeout > 86400:
                    errors.append("Child session timeout must be between 3,600 and 86,400 seconds.")
            if not errors:
                set_settings({
                    "session_timeout_seconds": str(timeout),
                    "child_session_timeout_seconds": str(child_timeout),
                })
                log_audit("family_session_settings_updated", "settings", actor_name=get_current_account()["display_name"])
                flash("Session settings saved.", "success")
                return redirect(url_for("parent_management.family_settings") + "#session")
        else:
            errors.append("Choose a valid settings section.")

        for error in errors:
            flash(error, "error")

    settings = get_public_settings()
    settings.update({
        "family_name": family["name"] if family else settings["family_name"],
        "timezone": get_setting("family_timezone", "America/Los_Angeles"),
        "country": get_setting("family_country", "United States"),
        "date_format": get_setting("family_date_format", "MM/DD/YYYY"),
    })
    return render_template("parent_management/family_settings.html", settings=settings)
