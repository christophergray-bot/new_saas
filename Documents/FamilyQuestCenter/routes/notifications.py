"""Family Quest Center developer documentation.

File: routes/notifications.py
Purpose: Defines Flask routes and request-handling workflows for notifications features.

Maintenance notes:
- Preserve tenant and family data isolation when changing queries.
- Keep route, template, and schema changes synchronized.
- Run regression tests before release packaging.
Documentation updated: 2026-07-31.
"""

from flask import Blueprint, flash, redirect, render_template, request, url_for

from models.notifications import dismiss_all_notifications, dismiss_notification, get_parent_notifications

notifications_blueprint = Blueprint("notifications", __name__, url_prefix="/parent/notifications")


@notifications_blueprint.route("/")
def center():
    """Handle the center workflow."""
    return render_template("parent/notifications.html", notifications=get_parent_notifications())


@notifications_blueprint.post("/dismiss")
def dismiss():
    """Handle the dismiss workflow."""
    key = request.form.get("notification_key", "").strip()
    if key:
        dismiss_notification(key)
        flash("Notification dismissed.", "success")
    return redirect(url_for("notifications.center"))


@notifications_blueprint.post("/dismiss-all")
def dismiss_all():
    """Handle the dismiss all workflow."""
    dismiss_all_notifications([item["key"] for item in get_parent_notifications()])
    flash("All current notifications dismissed.", "success")
    return redirect(url_for("notifications.center"))
