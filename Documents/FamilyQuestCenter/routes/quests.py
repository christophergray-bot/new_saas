"""Family Quest Center developer documentation.

File: routes/quests.py
Purpose: Defines Flask routes and request-handling workflows for quests features.

Maintenance notes:
- Preserve tenant and family data isolation when changing queries.
- Keep route, template, and schema changes synchronized.
- Run regression tests before release packaging.
Documentation updated: 2026-07-31.
"""

from flask import Blueprint, flash, redirect, render_template, request, url_for

from models.settings import get_public_settings
from services.content_packs import get_pack_source_map
from models.recurring_missions import get_active_schedule_summaries_by_chore

from models.chores import (
    create_chore,
    duplicate_chore,
    get_all_chores,
    get_chore,
    set_chore_active,
    update_chore,
)

quests_blueprint = Blueprint(
    "quests",
    __name__,
    url_prefix="/parent/quests",
)


@quests_blueprint.route("/")
def library():
    """Handle the library workflow."""
    chores = [c for c in get_all_chores() if c["active"]]
    search = request.args.get("q", "").strip().lower()
    difficulty = request.args.get("difficulty", "all")
    if search:
        chores = [c for c in chores if search in c["title"].lower() or search in (c["description"] or "").lower()]
    if difficulty.isdigit():
        chores = [c for c in chores if int(c["difficulty"]) == int(difficulty)]
    return render_template(
        "parent/quests/library.html", chores=chores,
        search_query=request.args.get("q", ""), selected_difficulty=difficulty,
        pack_sources=get_pack_source_map("quest", [c["id"] for c in chores]),
        assignment_summaries=get_active_schedule_summaries_by_chore(),
    )


@quests_blueprint.route("/new", methods=["GET", "POST"])
def new():

    """Handle the new workflow."""
    defaults = get_public_settings()

    if request.method == "POST":

        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        approval_required = request.form.get("approval_required") == "on"

        try:
            difficulty = int(request.form.get("difficulty", defaults["default_quest_difficulty"]))
            stars = int(request.form.get("stars", defaults["default_quest_stars"]))
        except ValueError:
            flash("Difficulty and stars must be numbers.", "error")
            return render_template("parent/quests/new.html", defaults=defaults)

        if not title:
            flash("Quest name is required.", "error")
            return render_template("parent/quests/new.html", defaults=defaults)

        if difficulty not in range(1, 6):
            flash("Difficulty must be between 1 and 5.", "error")
            return render_template("parent/quests/new.html", defaults=defaults)

        if stars < 0:
            flash("Stars cannot be negative.", "error")
            return render_template("parent/quests/new.html", defaults=defaults)

        create_chore(
            title=title,
            description=description,
            difficulty=difficulty,
            stars=stars,
            approval_required=approval_required,
        )

        flash("Quest created successfully.", "success")

        return redirect(url_for("quests.library"))

    return render_template("parent/quests/new.html", defaults=defaults)


@quests_blueprint.route("/<int:chore_id>/edit", methods=["GET", "POST"])
def edit(chore_id):

    """Handle the edit workflow."""
    chore = get_chore(chore_id)

    if chore is None:
        flash("Quest not found.", "error")
        return redirect(url_for("quests.library"))

    if request.method == "POST":

        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        approval_required = request.form.get("approval_required") == "on"

        try:
            difficulty = int(request.form.get("difficulty", 1))
            stars = int(request.form.get("stars", 10))
        except ValueError:
            flash("Difficulty and stars must be numbers.", "error")
            return render_template(
                "parent/quests/edit.html",
                chore=chore,
            )

        update_chore(
            chore_id=chore_id,
            title=title,
            description=description,
            difficulty=difficulty,
            stars=stars,
            approval_required=approval_required,
        )

        flash("Quest updated successfully.", "success")

        return redirect(url_for("quests.library"))

    return render_template(
        "parent/quests/edit.html",
        chore=chore,
    )
    
@quests_blueprint.post("/<int:chore_id>/toggle")
def toggle(chore_id):

    """Handle the toggle workflow."""
    chore = get_chore(chore_id)

    if chore is None:
        flash("Quest not found.", "error")
        return redirect(url_for("quests.library"))

    new_status = not bool(chore["active"])

    set_chore_active(
        chore_id=chore_id,
        active=new_status,
    )

    if new_status:
        flash("Quest restored.", "success")
    else:
        flash("Quest archived.", "success")

    return redirect(url_for("quests.library"))
    
@quests_blueprint.route("/<int:chore_id>/duplicate")
def duplicate(chore_id):

    """Handle the duplicate workflow."""
    duplicated = duplicate_chore(chore_id)

    if not duplicated:
        flash("Quest not found.", "error")
        return redirect(url_for("quests.library"))

    flash("Quest duplicated successfully.", "success")

    return redirect(url_for("quests.library"))