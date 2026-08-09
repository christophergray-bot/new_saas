"""Authentication and role helpers for hosted family accounts."""
from __future__ import annotations

from functools import wraps

from flask import abort, g, redirect, request, session, url_for

from database import get_db
from models.settings import get_setting, set_setting
from services.account_tokens import ensure_account_token_schema

ALLOWED_ROLES = {"owner", "parent", "caregiver"}


def get_current_account():
    """Retrieve current account."""
    if hasattr(g, "current_account"):
        return g.current_account
    account_id = session.get("account_user_id")
    if not account_id:
        g.current_account = None
        return None
    ensure_account_token_schema()
    row = get_db().execute(
        "SELECT id,email,display_name,email_verified,active,last_login_at,auth_version,COALESCE(platform_role, 'none') AS platform_role FROM account_users WHERE id=? AND active=1",
        (int(account_id),),
    ).fetchone()
    if row is None or int(session.get("auth_version", -1)) != int(row["auth_version"] or 0):
        session.clear()
        row = None
    g.current_account = row
    return row


def get_current_membership():
    """Retrieve current membership."""
    if hasattr(g, "current_membership"):
        return g.current_membership
    account = get_current_account()
    family_id = session.get("family_id")
    if account is None or family_id is None:
        g.current_membership = None
        return None
    row = get_db().execute(
        """SELECT fm.id,fm.family_id,fm.account_user_id,fm.role,fm.active,f.name AS family_name
           FROM family_memberships fm JOIN families f ON f.id=fm.family_id
           WHERE fm.account_user_id=? AND fm.family_id=? AND fm.active=1 AND f.status='active'""",
        (account["id"], int(family_id)),
    ).fetchone()
    if row is None:
        session.pop("family_id", None)
    g.current_membership = row
    return row


def authenticated_account_required(view):
    """Require a signed-in account, regardless of family membership."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if get_current_account() is None:
            return redirect(url_for("account.login", next=request.full_path.rstrip("?")))
        return view(*args, **kwargs)
    return wrapped


def account_required(view):
    """Require a normal family account and active family membership."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        account = get_current_account()
        if account is None:
            return redirect(url_for("account.login", next=request.full_path.rstrip("?")))
        if get_current_membership() is None:
            abort(403)
        return view(*args, **kwargs)
    return wrapped


def roles_required(*roles: str):
    """Handle the roles required workflow."""
    expected = set(roles)
    if not expected or not expected.issubset(ALLOWED_ROLES):
        raise ValueError("Unsupported account role")
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            """Handle the decorator workflow."""
            """Handle the wrapped workflow."""
            account = get_current_account()
            if account is None:
                return redirect(url_for("account.login", next=request.full_path.rstrip("?")))
            membership = get_current_membership()
            if membership is None:
                abort(403)
            if membership["role"] not in expected:
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator


def get_installation_owner_account_id() -> int | None:
    """Return the account that owns local installation-level developer tools."""
    configured = get_setting("installation_owner_account_id")
    try:
        owner_id = int(configured) if configured else None
    except (TypeError, ValueError):
        owner_id = None
    if owner_id is not None:
        exists = get_db().execute("SELECT 1 FROM account_users WHERE id=? AND active=1", (owner_id,)).fetchone()
        if exists:
            return owner_id
    row = get_db().execute(
        "SELECT id FROM account_users WHERE active=1 AND platform_role='application_owner' ORDER BY id LIMIT 1"
    ).fetchone()
    if row is None:
        return None
    owner_id = int(row["id"])
    set_setting("installation_owner_account_id", str(owner_id))
    return owner_id

def is_installation_owner() -> bool:
    account = get_current_account()
    if account is None:
        return False
    if account["platform_role"] == "application_owner":
        return True
    owner_id = get_installation_owner_account_id()
    return bool(owner_id is not None and int(account["id"]) == owner_id)

def installation_owner_required(view):
    """Restrict installation-wide developer controls to the first/local owner account."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if get_current_account() is None:
            return redirect(url_for("account.login", next=request.full_path.rstrip("?")))
        if not is_installation_owner():
            abort(403)
        return view(*args, **kwargs)
    return wrapped
