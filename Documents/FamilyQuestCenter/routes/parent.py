"""Family Quest Center developer documentation.

File: routes/parent.py
Purpose: Defines Flask routes and request-handling workflows for parent features.

Maintenance notes:
- Preserve tenant and family data isolation when changing queries.
- Keep route, template, and schema changes synchronized.
- Run regression tests before release packaging.
Documentation updated: 2026-07-31.
"""

from datetime import date

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from models.administration import log_audit
from services.mission_service import (
    generate_missions_for_date,
    count_missions_for_date,
    count_pending_mission_approvals,
)
from services.adventure_service import count_pending_journey_approvals
from models.journeys import count_pending_v2_journey_approvals, count_pending_adventure_approvals
from models.settings import get_public_settings, get_setting, set_setting, set_settings
from models.dashboard import count_active_adventures, get_active_adventures, get_dashboard_pending_approvals, get_recent_activity, get_weekly_family_stats
from models.users import get_children
from models.rewards import get_reward_requests
from models.cosmetics import get_character_profile


parent_blueprint = Blueprint("parent", __name__, url_prefix="/parent")


def _valid_four_digit_pin(pin: str) -> bool:
    """Handle the valid four digit pin workflow."""
    return len(pin) == 4 and pin.isdigit()


@parent_blueprint.route("/")
def dashboard():
    """Handle the dashboard workflow."""
    from services.onboarding import family_setup_complete
    if not family_setup_complete():
        return redirect(url_for("onboarding.family_setup"))
    generate_missions_for_date(date.today())
    today = date.today().isoformat()
    settings = get_public_settings()
    active_adventures = get_active_adventures()
    pending_reward_requests = list(get_reward_requests(status="pending"))
    pending_quest_approval_count = count_pending_mission_approvals()
    pending_adventure_approval_count = (
        count_pending_journey_approvals()
        + count_pending_v2_journey_approvals()
        + count_pending_adventure_approvals()
    )
    children = []
    for child in get_children():
        if not child["active"]:
            continue
        child_data = dict(child)
        profile = get_character_profile(child)
        child_data["avatar_icon"] = (profile.get("avatar") or {}).get("icon") or child["initial"]
        child_data["avatar_image"] = (profile.get("avatar") or {}).get("image")
        children.append(child_data)
    return render_template(
        "parent/dashboard.html",
        children=children,
        assigned_today_count=count_missions_for_date(today),
        pending_approval_count=(
            pending_quest_approval_count
            + pending_adventure_approval_count
            + len(pending_reward_requests)
        ),
        pending_quest_approval_count=pending_quest_approval_count,
        pending_adventure_approval_count=pending_adventure_approval_count,
        family_name=settings["family_name"],
        pending_approvals=get_dashboard_pending_approvals(),
        pending_reward_requests=pending_reward_requests[:5],
        pending_reward_request_count=len(pending_reward_requests),
        active_adventures=active_adventures,
        active_adventure_count=count_active_adventures(),
        weekly_stats=get_weekly_family_stats(),
    )


@parent_blueprint.route("/settings", methods=["GET", "POST"])
def settings():
    """Preserve the legacy settings URL and direct users to Family Settings."""
    return redirect(url_for("parent_management.family_settings"))
