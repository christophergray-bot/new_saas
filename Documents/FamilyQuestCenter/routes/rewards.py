"""Family Quest Center developer documentation.

File: routes/rewards.py
Purpose: Defines Flask routes and request-handling workflows for rewards features.

Maintenance notes:
- Preserve tenant and family data isolation when changing queries.
- Keep route, template, and schema changes synchronized.
- Run regression tests before release packaging.
Documentation updated: 2026-07-31.
"""

from pathlib import Path
from uuid import uuid4

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from werkzeug.utils import secure_filename

from services.content_packs import get_pack_source_map

from models.rewards import (
    approve_request, create_category, deny_request, get_categories, get_reward,
    get_reward_requests, get_rewards, mark_redeemed, remove_reward_image,
    save_reward, set_category_active, set_reward_active,
)

rewards_blueprint = Blueprint("rewards", __name__, url_prefix="/parent/rewards")
ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}


def _save_uploaded_image(upload) -> str | None:
    """Handle the save uploaded image workflow."""
    if not upload or not upload.filename:
        return None
    filename = secure_filename(upload.filename)
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if extension not in ALLOWED_IMAGE_EXTENSIONS:
        raise ValueError("Reward images must be PNG, JPG, GIF, or WEBP files.")
    upload_dir = Path(current_app.root_path) / "static" / "uploads" / "rewards"
    upload_dir.mkdir(parents=True, exist_ok=True)
    saved_name = f"{uuid4().hex}.{extension}"
    upload.save(upload_dir / saved_name)
    return saved_name


@rewards_blueprint.route("/")
def manager():
    """Handle the manager workflow."""
    rows = list(get_rewards(include_inactive=False))
    search = request.args.get("q", "").strip().lower()
    if search:
        rows = [r for r in rows if search in r["name"].lower() or search in (r["description"] or "").lower()]
    return render_template(
        "parent/rewards/manager.html", rewards=rows,
        categories=get_categories(include_inactive=False),
        search_query=request.args.get("q", ""),
        pack_sources=get_pack_source_map("reward", [r["id"] for r in rows]),
    )


@rewards_blueprint.route("/new", methods=["GET", "POST"])
@rewards_blueprint.route("/<int:reward_id>/edit", methods=["GET", "POST"])
def edit(reward_id: int | None = None):
    """Handle the edit workflow."""
    reward = get_reward(reward_id) if reward_id else None
    if reward_id and reward is None:
        abort(404)
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        try:
            cost = int(request.form.get("cost", "0"))
            quantity_text = request.form.get("quantity", "").strip()
            quantity = int(quantity_text) if quantity_text else None
            category_text = request.form.get("category_id", "").strip()
            category_id = int(category_text) if category_text else None
            image_filename = _save_uploaded_image(request.files.get("reward_image"))
        except ValueError as exc:
            flash(str(exc), "error")
        else:
            if not name:
                flash("Reward name is required.", "error")
            elif cost < 1:
                flash("Reward cost must be at least 1 star.", "error")
            elif quantity is not None and quantity < 0:
                flash("Quantity cannot be negative.", "error")
            else:
                active_status = bool(reward["active"]) if reward is not None else True
                save_reward(
                    reward_id, category_id, name, request.form.get("description", ""),
                    request.form.get("icon", "🎁"), cost, quantity,
                    "requires_approval" in request.form, active_status,
                    image_filename,
                )
                if reward_id and "remove_image" in request.form and not image_filename:
                    remove_reward_image(reward_id)
                flash("Reward saved successfully.", "success")
                return redirect(url_for("rewards.manager"))
    return render_template("parent/rewards/edit.html", reward=reward, categories=get_categories(False))


@rewards_blueprint.route("/<int:reward_id>/toggle", methods=["POST"])
def toggle_reward(reward_id: int):
    """Handle the toggle reward workflow."""
    reward = get_reward(reward_id)
    if reward is None:
        abort(404)
    new_status = not bool(reward["active"])
    set_reward_active(reward_id, new_status)
    flash("Reward restored." if new_status else "Reward archived.", "success")
    return redirect(url_for("rewards.manager"))


@rewards_blueprint.route("/categories", methods=["POST"])
def add_category():
    """Handle the add category workflow."""
    name = request.form.get("name", "").strip()
    if not name:
        flash("Category name is required.", "error")
    else:
        try:
            create_category(name, request.form.get("icon", "🎁"), int(request.form.get("display_order", 0)))
            flash("Reward category created.", "success")
        except Exception:
            flash("That category already exists or could not be created.", "error")
    return redirect(url_for("rewards.manager"))


@rewards_blueprint.route("/categories/<int:category_id>/toggle", methods=["POST"])
def toggle_category(category_id: int):
    """Handle the toggle category workflow."""
    categories = {row["id"]: row for row in get_categories()}
    category = categories.get(category_id)
    if category is None:
        abort(404)
    new_status = not bool(category["active"])
    set_category_active(category_id, new_status)
    flash("Reward category restored." if new_status else "Reward category archived.", "success")
    return redirect(url_for("rewards.manager"))


@rewards_blueprint.route("/requests")
def requests_queue():
    """Handle the requests queue workflow."""
    status = request.args.get("status", "pending")
    if status not in {"pending", "approved", "denied", "redeemed", "all"}:
        status = "pending"
    rows = get_reward_requests(status=None if status == "all" else status)
    return render_template("parent/rewards/requests.html", reward_requests=rows, selected_status=status)


@rewards_blueprint.route("/requests/<int:request_id>/approve", methods=["POST"])
def approve(request_id: int):
    """Handle the approve workflow."""
    success, message = approve_request(request_id, notes=request.form.get("notes", ""))
    flash(message, "success" if success else "error")
    return redirect(url_for("rewards.requests_queue"))


@rewards_blueprint.route("/requests/<int:request_id>/deny", methods=["POST"])
def deny(request_id: int):
    """Handle the deny workflow."""
    success, message = deny_request(request_id, notes=request.form.get("notes", ""))
    flash(message, "success" if success else "error")
    return redirect(url_for("rewards.requests_queue"))


@rewards_blueprint.route("/requests/<int:request_id>/redeem", methods=["POST"])
def redeem(request_id: int):
    """Handle the redeem workflow."""
    success, message = mark_redeemed(request_id)
    flash(message, "success" if success else "error")
    return redirect(url_for("rewards.requests_queue", status="approved"))
