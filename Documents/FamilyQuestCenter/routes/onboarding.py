"""Parent Family Setup Adventure and child Explorer Training."""
from __future__ import annotations

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for

from models.users import get_user_by_id
from services.account_auth import account_required
from services.onboarding import (
    child_training_complete,
    complete_child_training,
    complete_family_setup,
    get_setup_status,
)

onboarding_blueprint = Blueprint("onboarding", __name__, url_prefix="/getting-started")


@onboarding_blueprint.route("/")
@account_required
def family_setup():
    """Handle the family setup workflow."""
    if not session.get("parent_authenticated"):
        return redirect(url_for("auth.login", next=request.path))
    status = get_setup_status()
    if status["setup_completed"]:
        return redirect(url_for("parent.dashboard"))
    return render_template("onboarding/family_setup.html", status=status)


@onboarding_blueprint.route("/finish", methods=["POST"])
@account_required
def finish_family_setup():
    """Handle the finish family setup workflow."""
    if not session.get("parent_authenticated"):
        return redirect(url_for("auth.login", next=url_for("onboarding.family_setup")))

    status = get_setup_status()
    if not status["ready"]:
        flash("Complete the remaining family setup steps first.", "warning")
        return redirect(url_for("onboarding.family_setup"))

    complete_family_setup()
    choice = request.form.get("choice", "explore")

    if choice == "lock":
        session.pop("parent_authenticated", None)
        return render_template("onboarding/family_ready.html")

    flash("Family setup complete. Take some time to explore your Parent Dashboard.", "success")
    return redirect(url_for("parent.dashboard"))


@onboarding_blueprint.route("/explorer/<int:user_id>")
@account_required
def explorer_training(user_id: int):
    """Handle the explorer training workflow."""
    child = get_user_by_id(user_id)
    if child is None or child["role"] != "child":
        abort(404)
    if child_training_complete(user_id):
        return redirect(url_for("child.dashboard", user_id=user_id, trained=1))
    try:
        step = int(request.args.get("step", "1"))
    except ValueError:
        step = 1
    step = max(1, min(step, 7))
    return render_template("onboarding/explorer_training.html", child=child, step=step)


@onboarding_blueprint.route("/explorer/<int:user_id>/complete", methods=["POST"])
@account_required
def explorer_training_complete(user_id: int):
    """Handle the explorer training complete workflow."""
    child = get_user_by_id(user_id)
    if child is None or child["role"] != "child":
        abort(404)
    complete_child_training(user_id)
    flash("🏆 Explorer Training complete! You're ready for your first real mission.", "achievement")
    return redirect(url_for("child.dashboard", user_id=user_id, trained=1))
