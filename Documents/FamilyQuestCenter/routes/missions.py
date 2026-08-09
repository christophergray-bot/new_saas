"""Family Quest Center developer documentation.

File: routes/missions.py
Purpose: Defines Flask routes and request-handling workflows for missions features.

Maintenance notes:
- Preserve tenant and family data isolation when changing queries.
- Keep route, template, and schema changes synchronized.
- Run regression tests before release packaging.
Documentation updated: 2026-07-31.
"""

from datetime import date

from flask import Blueprint, flash, redirect, render_template, request, url_for

from services.mission_service import (
    generate_missions_for_date,
    list_active_children,
    list_active_quests,
    list_missions_for_date,
)
from models.recurring_missions import (
    create_schedule,
    get_schedule,
    get_schedules,
    set_schedule_active,
    unassign_schedule,
    update_schedule,
)


missions_blueprint = Blueprint(
    "missions",
    __name__,
    url_prefix="/parent/missions",
)


WEEKDAYS = [
    (0, "Monday"),
    (1, "Tuesday"),
    (2, "Wednesday"),
    (3, "Thursday"),
    (4, "Friday"),
    (5, "Saturday"),
    (6, "Sunday"),
]


def _schedule_form_values():
    """Read and normalize Mission Builder form fields."""

    chore_id = request.form.get("chore_id", type=int)
    child_id = request.form.get("child_id", type=int)
    schedule_type = request.form.get("schedule_type", "").strip().lower()
    start_date = request.form.get("start_date", "").strip()
    end_date = request.form.get("end_date", "").strip() or None
    day_of_month = request.form.get("day_of_month", type=int)

    days_of_week = []

    if schedule_type == "weekly":
        weekly_day = request.form.get("weekly_day", type=int)

        if weekly_day is not None:
            days_of_week = [weekly_day]

    elif schedule_type == "custom":
        for value in request.form.getlist("custom_days"):
            try:
                days_of_week.append(int(value))
            except ValueError:
                continue

    return {
        "chore_id": chore_id,
        "child_id": child_id,
        "schedule_type": schedule_type,
        "start_date": start_date,
        "end_date": end_date,
        "days_of_week": days_of_week,
        "day_of_month": day_of_month,
    }


def _validate_common_fields(values):
    """Validate fields shared by all schedule types."""

    if values["chore_id"] is None:
        return "Select a quest."

    if values["child_id"] is None:
        return "Select a child."

    if not values["start_date"]:
        return "Select a start date."

    return None


@missions_blueprint.route("/", methods=["GET"])
def today():
    """Automatically generate and display today's assignments."""

    # Generate today's scheduled quests (safe to call repeatedly)
    generate_missions_for_date(date.today())

    today_date = date.today().isoformat()
    assignments = list_missions_for_date(today_date)

    return render_template(
        "parent/missions/today.html",
        assignments=assignments,
        today_date=today_date,
    )


@missions_blueprint.route("/generate", methods=["POST"])
def generate_today():
    """Generate today's assignments from active quest schedules."""

    result = generate_missions_for_date(date.today())

    if result["created"]:
        flash(
            f'{result["created"]} scheduled quest(s) generated.',
            "success",
        )
    else:
        flash("No new scheduled quests were generated.", "info")

    if result["skipped"]:
        flash(
            f'{result["skipped"]} quest(s) already existed and were skipped.',
            "warning",
        )

    return redirect(url_for("missions.today"))


@missions_blueprint.route("/schedules", methods=["GET"])
def schedules():
    """Display active and archived Mission Builder entries."""

    schedule_rows = get_schedules(include_inactive=False)

    return render_template(
        "parent/missions/schedules.html",
        schedules=schedule_rows,
        weekday_names=dict(WEEKDAYS),
    )


@missions_blueprint.route("/schedules/add", methods=["GET", "POST"])
def add_schedule():
    """Create a new recurring mission definition."""

    children = list_active_children()
    chores = list_active_quests()

    if request.method == "POST":
        values = _schedule_form_values()
        child_ids = [int(value) for value in request.form.getlist("child_ids") if value.isdigit()]
        values["child_id"] = child_ids[0] if child_ids else None
        common_error = _validate_common_fields(values)

        if common_error:
            flash(common_error, "error")
        else:
            try:
                created_count = 0
                for child_id in child_ids:
                    child_values = dict(values)
                    child_values["child_id"] = child_id
                    create_schedule(**child_values)
                    created_count += 1
            except ValueError as error:
                flash(str(error), "error")
            else:
                flash(
                    f"Mission assigned to {created_count} child" + ("ren." if created_count != 1 else "."),
                    "success",
                )
                return_to = request.form.get("return_to", "").strip()
                if return_to == "quest_library":
                    return redirect(url_for("quests.library"))
                return redirect(url_for("missions.schedules"))

    selected_chore_id = request.args.get("chore_id", type=int)
    return_to = request.args.get("return_to", "").strip()

    return render_template(
        "parent/missions/schedule_form.html",
        page_title="Assign Mission" if selected_chore_id else "Build a Mission",
        form_action=url_for("missions.add_schedule"),
        submit_label="Save Mission",
        children=children,
        chores=chores,
        weekdays=WEEKDAYS,
        schedule=None,
        selected_custom_days=[],
        selected_weekly_day=None,
        today_date=date.today().isoformat(),
        selected_chore_id=selected_chore_id,
        return_to=return_to,
    )


@missions_blueprint.route(
    "/schedules/<int:schedule_id>/edit",
    methods=["GET", "POST"],
)
def edit_schedule(schedule_id: int):
    """Edit an existing recurring mission definition."""

    schedule = get_schedule(schedule_id)

    if schedule is None:
        flash("Mission not found.", "error")
        return redirect(url_for("missions.schedules"))

    children = list_active_children()
    chores = list_active_quests()

    if request.method == "POST":
        values = _schedule_form_values()
        common_error = _validate_common_fields(values)

        if common_error:
            flash(common_error, "error")
        else:
            try:
                updated = update_schedule(
                    schedule_id=schedule_id,
                    **values,
                )
            except ValueError as error:
                flash(str(error), "error")
            else:
                if updated:
                    flash("Mission updated successfully.", "success")
                else:
                    flash("No mission was updated.", "warning")

                return redirect(url_for("missions.schedules"))

    stored_days = {
        int(value)
        for value in (schedule["days_of_week"] or "").split(",")
        if value.strip()
    }

    selected_weekly_day = None

    if schedule["schedule_type"] == "weekly" and stored_days:
        selected_weekly_day = next(iter(stored_days))

    return render_template(
        "parent/missions/schedule_form.html",
        page_title="Edit Mission",
        form_action=url_for(
            "missions.edit_schedule",
            schedule_id=schedule_id,
        ),
        submit_label="Update Mission",
        children=children,
        chores=chores,
        weekdays=WEEKDAYS,
        schedule=schedule,
        selected_custom_days=stored_days,
        selected_weekly_day=selected_weekly_day,
        today_date=date.today().isoformat(),
    )


@missions_blueprint.route(
    "/schedules/<int:schedule_id>/toggle",
    methods=["POST"],
)
def toggle_schedule(schedule_id: int):
    """Archive or restore a recurring mission."""

    schedule = get_schedule(schedule_id)

    if schedule is None:
        flash("Mission not found.", "error")
        return redirect(url_for("missions.schedules"))

    new_active_status = not bool(schedule["active"])
    updated = set_schedule_active(schedule_id, new_active_status)

    if not updated:
        flash("The Mission assignment could not be updated.", "error")
    elif new_active_status:
        flash("Mission assignment resumed.", "success")
    else:
        flash("Mission assignment paused. Completed history was preserved.", "success")

    return_to = request.form.get("return_to", "").strip()
    if return_to == "quest_library":
        return redirect(url_for("quests.library"))
    return redirect(url_for("missions.schedules"))


@missions_blueprint.post("/schedules/<int:schedule_id>/unassign")
def unassign(schedule_id: int):
    """End a Quest assignment without deleting completed Mission history."""

    schedule = get_schedule(schedule_id)
    if schedule is None:
        flash("Mission assignment not found.", "error")
    elif unassign_schedule(schedule_id):
        flash(
            f"{schedule['title']} is no longer assigned to {schedule['child_name']}. "
            "Completed Mission history was preserved.",
            "success",
        )
    else:
        flash("The Mission assignment was already inactive.", "info")

    return_to = request.form.get("return_to", "").strip()
    if return_to == "quest_library":
        return redirect(url_for("quests.library"))
    return redirect(url_for("missions.schedules"))
