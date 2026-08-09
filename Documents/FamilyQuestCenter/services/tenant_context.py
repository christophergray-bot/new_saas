"""Request-level tenant context and ownership helpers.

Sprint 3.0-B keeps the local fallback for backward compatibility. Sprint 3.0-C
will resolve the family from the authenticated account membership.
"""
from __future__ import annotations

from functools import wraps

from flask import abort, g, session

from database import get_db


def get_current_family_id() -> int:
    """Retrieve current family id."""
    cached = getattr(g, "current_family_id", None)
    if cached is not None:
        return int(cached)

    family_id = session.get("family_id")
    account_user_id = session.get("account_user_id")
    if account_user_id is not None:
        row = get_db().execute(
            """SELECT fm.family_id FROM family_memberships fm JOIN families f ON f.id=fm.family_id
               WHERE fm.account_user_id=? AND fm.family_id=? AND fm.active=1 AND f.status='active'""",
            (int(account_user_id), int(family_id)) if family_id is not None else (int(account_user_id), -1),
        ).fetchone()
        if row is None:
            session.pop("family_id", None)
            raise RuntimeError("The signed-in account has no active membership for this family.")
        family_id = int(row[0])
    elif family_id is None:
        row = get_db().execute(
            "SELECT id FROM families WHERE status='active' ORDER BY id LIMIT 1"
        ).fetchone()
        if row is None:
            raise RuntimeError("No active family is configured.")
        family_id = int(row[0])
        session["family_id"] = family_id

    row = get_db().execute(
        "SELECT id FROM families WHERE id=? AND status='active'", (int(family_id),)
    ).fetchone()
    if row is None:
        session.pop("family_id", None)
        raise RuntimeError("The selected family is unavailable.")

    g.current_family_id = int(family_id)
    return int(family_id)


def get_current_family():
    """Retrieve current family."""
    return get_db().execute(
        "SELECT id,name,slug,status FROM families WHERE id=?",
        (get_current_family_id(),),
    ).fetchone()


def family_owns(table: str, record_id: int) -> bool:
    """Handle the family owns workflow."""
    allowed = {
        "users", "chores", "assignments", "quest_schedules", "quest_chains",
        "quest_chain_instances", "journeys", "adventures_v2",
        "adventure_instances_v2", "rewards", "reward_requests",
        "family_challenges",
    }
    if table not in allowed:
        raise ValueError(f"Unsupported tenant-owned table: {table}")
    return get_db().execute(
        f'SELECT 1 FROM "{table}" WHERE id=? AND family_id=?',
        (record_id, get_current_family_id()),
    ).fetchone() is not None


def require_family_record(table: str, record_id: int) -> None:
    """Handle the require family record workflow."""
    if not family_owns(table, record_id):
        abort(404)


def family_scoped_route(table: str, parameter: str):
    """Decorator that blocks cross-family URL-ID access before route execution."""
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            """Handle the decorator workflow."""
            """Handle the wrapped workflow."""
            record_id = kwargs.get(parameter)
            if record_id is None or not family_owns(table, int(record_id)):
                abort(404)
            return view(*args, **kwargs)
        return wrapped
    return decorator
