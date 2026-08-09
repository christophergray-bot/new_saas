"""Family Quest Center developer documentation.

File: routes/achievements.py
Purpose: Defines Flask routes and request-handling workflows for achievements features.

Maintenance notes:
- Preserve tenant and family data isolation when changing queries.
- Keep route, template, and schema changes synchronized.
- Run regression tests before release packaging.
Documentation updated: 2026-07-31.
"""

from __future__ import annotations

import sqlite3

from flask import Blueprint, flash, redirect, render_template, request, url_for

from services.content_packs import get_pack_source_map

from models.achievements import (
    REQUIREMENT_LABELS,
    create_achievement,
    get_achievement,
    get_achievement_admin_list,
    set_achievement_active,
    update_achievement,
)


achievements_blueprint = Blueprint(
    "achievements",
    __name__,
    url_prefix="/parent/achievements",
)


def _parse_form():
    """Handle the parse form workflow."""
    name = request.form.get("name", "").strip()
    description = request.form.get("description", "").strip()
    icon = request.form.get("icon", "🏆").strip() or "🏆"
    category = request.form.get("category", "General").strip() or "General"
    requirement_type = request.form.get("requirement_type", "").strip()
    hidden = request.form.get("hidden") == "on"

    errors = []
    try:
        requirement_value = int(request.form.get("requirement_value", "0"))
        xp_reward = int(request.form.get("xp_reward", "0"))
        star_reward = int(request.form.get("star_reward", "0"))
    except (TypeError, ValueError):
        errors.append("Requirement and reward values must be whole numbers.")
        requirement_value = xp_reward = star_reward = 0

    if not name or len(name) > 100:
        errors.append("Achievement name must be between 1 and 100 characters.")
    if not description or len(description) > 500:
        errors.append("Description must be between 1 and 500 characters.")
    if len(icon) > 12:
        errors.append("Icon must be 12 characters or fewer.")
    if len(category) > 50:
        errors.append("Category must be 50 characters or fewer.")
    if requirement_type not in REQUIREMENT_LABELS:
        errors.append("Select a valid achievement requirement.")
    if requirement_value < 1 or requirement_value > 1_000_000:
        errors.append("Requirement value must be between 1 and 1,000,000.")
    if xp_reward < 0 or xp_reward > 100_000:
        errors.append("XP reward must be between 0 and 100,000.")
    if star_reward < 0 or star_reward > 100_000:
        errors.append("Star reward must be between 0 and 100,000.")

    return {
        "name": name,
        "description": description,
        "icon": icon,
        "category": category,
        "requirement_type": requirement_type,
        "requirement_value": requirement_value,
        "xp_reward": xp_reward,
        "star_reward": star_reward,
        "hidden": hidden,
    }, errors


@achievements_blueprint.route("/")
def manager():
    """Handle the manager workflow."""
    search = request.args.get("q", "").strip()
    status = "active"
    requirement = request.args.get("requirement", "all")
    rows = get_achievement_admin_list(search, status, requirement)
    return render_template(
        "parent/achievements/manager.html",
        achievements=rows,
        search_query=search,
        selected_status=status,
        selected_requirement=requirement,
        requirement_labels=REQUIREMENT_LABELS,
        pack_sources=get_pack_source_map("achievement", [r["id"] for r in rows]),
    )


@achievements_blueprint.route("/new", methods=["GET", "POST"])
def new():
    flash("Achievements are built in and progress automatically.", "warning")
    return redirect(url_for("achievements.manager"))


def _legacy_new_disabled():
    """Handle the new workflow."""
    if request.method == "POST":
        values, errors = _parse_form()
        if errors:
            for error in errors:
                flash(error, "error")
        else:
            try:
                create_achievement(**values)
            except sqlite3.IntegrityError:
                flash("An achievement with that name already exists.", "error")
            else:
                flash("Achievement created successfully.", "success")
                return redirect(url_for("achievements.manager"))

    return render_template(
        "parent/achievements/form.html",
        achievement=None,
        requirement_labels=REQUIREMENT_LABELS,
    )


@achievements_blueprint.route("/<int:achievement_id>/edit", methods=["GET", "POST"])
def edit(achievement_id):
    flash("Built-in achievements cannot be edited.", "warning")
    return redirect(url_for("achievements.manager"))


def _legacy_edit_disabled(achievement_id):
    """Handle the edit workflow."""
    achievement = get_achievement(achievement_id)
    if achievement is None:
        flash("Achievement not found.", "error")
        return redirect(url_for("achievements.manager"))

    if request.method == "POST":
        values, errors = _parse_form()
        if errors:
            for error in errors:
                flash(error, "error")
        else:
            try:
                update_achievement(achievement_id, **values)
            except sqlite3.IntegrityError:
                flash("An achievement with that name already exists.", "error")
            else:
                flash("Achievement updated successfully.", "success")
                return redirect(url_for("achievements.manager"))

    return render_template(
        "parent/achievements/form.html",
        achievement=achievement,
        requirement_labels=REQUIREMENT_LABELS,
    )


@achievements_blueprint.route("/<int:achievement_id>/toggle", methods=["POST"])
def toggle(achievement_id):
    flash("Built-in achievements cannot be archived.", "warning")
    return redirect(url_for("achievements.manager"))


def _legacy_toggle_disabled(achievement_id):
    """Handle the toggle workflow."""
    achievement = get_achievement(achievement_id)
    if achievement is None:
        flash("Achievement not found.", "error")
        return redirect(url_for("achievements.manager"))

    new_status = not bool(achievement["active"])
    set_achievement_active(achievement_id, new_status)
    flash("Achievement restored." if new_status else "Achievement archived.", "success")
    return redirect(url_for("achievements.manager"))
