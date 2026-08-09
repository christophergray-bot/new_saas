"""Family Quest Center developer documentation.

File: routes/approvals.py
Purpose: Defines Flask routes and request-handling workflows for approvals features.

Maintenance notes:
- Preserve tenant and family data isolation when changing queries.
- Keep route, template, and schema changes synchronized.
- Run regression tests before release packaging.
Documentation updated: 2026-07-31.
"""

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from models.administration import log_audit
from models.journeys import (
    approve_v2_journey,
    get_journey_instance,
    list_pending_v2_journey_approvals,
    return_v2_journey,
    get_adventure_instance,
    list_pending_adventure_approvals,
    approve_adventure_instance,
    return_adventure_instance,
)
from services.mission_service import approve_mission, get_mission, list_pending_mission_approvals, return_mission
from services.adventure_service import approve_journey, get_journey_assignment, list_pending_journey_approvals, return_journey
from services.content_packs import approve_pack_request, deny_pack_request, get_pack_request, list_pending_pack_requests

approvals_blueprint = Blueprint("approvals", __name__, url_prefix="/parent/approvals")


def _mission_rows():
    """Handle the mission rows workflow."""
    return [{**dict(row), "activity_kind": "mission", "type_label": "Mission"} for row in list_pending_mission_approvals()]


def _legacy_rows():
    """Handle the legacy rows workflow."""
    return [{**dict(row), "activity_kind": "legacy_journey", "type_label": "Journey"} for row in list_pending_journey_approvals()]


def _all_pending():
    """Handle the all pending workflow."""
    rows = _mission_rows() + _legacy_rows() + list_pending_v2_journey_approvals() + list_pending_adventure_approvals() + list_pending_pack_requests()
    rows.sort(key=lambda row: row.get("completed_at") or "")
    return rows


def _activity(kind, activity_id):
    """Handle the activity workflow."""
    if kind == "mission":
        return get_mission(activity_id), approve_mission, return_mission
    if kind == "legacy_journey":
        return get_journey_assignment(activity_id), approve_journey, return_journey
    if kind == "journey":
        return get_journey_instance(activity_id), approve_v2_journey, return_v2_journey
    if kind == "adventure":
        return get_adventure_instance(activity_id), approve_adventure_instance, return_adventure_instance
    return None, None, None


@approvals_blueprint.route("/")
def queue():
    """Handle the queue workflow."""
    selected_filter = request.args.get("type", "all")
    assignments = _all_pending()
    if selected_filter == "missions":
        assignments = [row for row in assignments if row["activity_kind"] == "mission"]
    elif selected_filter == "journeys":
        assignments = [row for row in assignments if row["activity_kind"] in {"legacy_journey", "journey", "adventure"}]
    elif selected_filter == "packs":
        assignments = [row for row in assignments if row["activity_kind"] == "pack_request"]
    return render_template("parent/approvals/queue.html", assignments=assignments, selected_filter=selected_filter)


@approvals_blueprint.post("/<string:activity_kind>/<int:activity_id>/approve")
def approve(activity_kind, activity_id):
    """Handle the approve workflow."""
    if activity_kind == "pack_request":
        request_row = get_pack_request(activity_id)
        if request_row is None:
            abort(404)
        try:
            result = approve_pack_request(activity_id)
        except ValueError as exc:
            flash(str(exc), "warning")
            return redirect(url_for("approvals.queue", type="packs"))
        if result is None:
            flash("This pack request is no longer waiting for approval.", "warning")
        else:
            log_audit("PACK_REQUEST_APPROVED", "content_pack_request", activity_id, f"Approved {request_row['title']} for the family")
            flash(f"{request_row['title']} approved and installed for your family.", "success")
        return redirect(url_for("approvals.queue", type="packs"))

    assignment, approve_activity, _ = _activity(activity_kind, activity_id)
    if assignment is None: abort(404)
    result = approve_activity(activity_id)
    if not result:
        flash("This activity is no longer waiting for approval.", "warning")
        return redirect(url_for("approvals.queue"))

    log_audit(f"{activity_kind.upper()}_APPROVED", "activity", activity_id, f"Approved {assignment['title']} for child ID {assignment['child_id']}")
    if activity_kind == "adventure":
        flash(f"Adventure approved for {assignment['child_name']}. The child celebration is ready.", "success")
    elif activity_kind == "journey":
        flash(f"Chapter approved! {assignment['xp_reward']} XP awarded.", "success")
    else:
        flash(f"Activity approved! {assignment['stars']} stars and {assignment['xp_reward']} XP awarded.", "success")
        if result.get("chain_completed"):
            chain=result["chain_completed"]
            flash(f"Adventure completion approved for {assignment['child_name']}. The child celebration is ready.", "success")
    return redirect(url_for("approvals.queue"))


@approvals_blueprint.post("/<string:activity_kind>/<int:activity_id>/return")
def reject(activity_kind, activity_id):
    """Handle the reject workflow."""
    if activity_kind == "pack_request":
        request_row = get_pack_request(activity_id)
        if request_row is None:
            abort(404)
        result = deny_pack_request(activity_id)
        if result is None:
            flash("This pack request is no longer waiting for approval.", "warning")
        else:
            log_audit("PACK_REQUEST_DENIED", "content_pack_request", activity_id, f"Denied {request_row['title']} for the family")
            flash("Pack request denied.", "success")
        return redirect(url_for("approvals.queue", type="packs"))

    assignment, _, return_activity = _activity(activity_kind, activity_id)
    if assignment is None: abort(404)
    if not return_activity(activity_id):
        flash("This activity is no longer waiting for approval.", "warning")
    else:
        log_audit(f"{activity_kind.upper()}_RETURNED", "activity", activity_id, f"Returned {assignment['title']} to child")
        flash("Activity returned to the child.", "success")
    return redirect(url_for("approvals.queue"))


@approvals_blueprint.post("/bulk")
def bulk_action():
    """Handle the bulk action workflow."""
    action=request.form.get("action", "")
    selected=request.form.getlist("activity_keys")
    if not selected:
        flash("Select at least one activity.", "warning")
        return redirect(url_for("approvals.queue"))
    changed=0
    for key in selected:
        try: kind, raw_id=key.split(":",1); activity_id=int(raw_id)
        except (ValueError, TypeError): continue
        if kind == "pack_request":
            try:
                if action == "approve" and approve_pack_request(activity_id): changed += 1
                elif action == "return" and deny_pack_request(activity_id): changed += 1
            except ValueError:
                continue
            continue
        assignment, approve_activity, return_activity=_activity(kind,activity_id)
        if assignment is None: continue
        if action=="approve" and approve_activity(activity_id): changed+=1
        elif action=="return" and return_activity(activity_id): changed+=1
    flash(f"{'Approved' if action=='approve' else 'Returned'} {changed} selected activit{'y' if changed==1 else 'ies'}.", "success")
    return redirect(url_for("approvals.queue"))
