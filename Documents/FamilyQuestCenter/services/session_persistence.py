"""Session persistence helpers for account Remember Me behavior."""
from __future__ import annotations

from datetime import timedelta

from flask import current_app, session

from models.settings import get_global_setting


def configured_remember_days() -> int:
    """Return the validated installation-wide Remember Me duration."""
    fallback_days = int(current_app.config.get("REMEMBER_ME_DAYS", 30))
    try:
        remember_days = int(get_global_setting("remember_me_days", fallback_days))
    except (TypeError, ValueError):
        remember_days = fallback_days
    return max(1, min(365, remember_days))


def apply_remember_me(remember: bool) -> None:
    """Apply and record the persistence choice for the signed-in account."""
    remembered = bool(remember)
    session["remember_me"] = remembered
    session.permanent = remembered

    if remembered:
        remember_days = configured_remember_days()
        session["remember_me_days"] = remember_days
        current_app.permanent_session_lifetime = timedelta(days=remember_days)
    else:
        session.pop("remember_me_days", None)


def restore_session_persistence() -> None:
    """Restore the selected lifetime on every request, including other workers.

    Parent accounts pass through a separate PIN request after account login.
    Recording the choice in the signed session prevents that request from
    replacing the selected Remember Me behavior.
    """
    if "remember_me" not in session:
        return

    remembered = bool(session.get("remember_me"))
    session.permanent = remembered
    if not remembered:
        return

    try:
        remember_days = int(session.get("remember_me_days", configured_remember_days()))
    except (TypeError, ValueError):
        remember_days = configured_remember_days()
    remember_days = max(1, min(365, remember_days))
    current_app.permanent_session_lifetime = timedelta(days=remember_days)
