"""Family Quest Center developer documentation.

File: routes/reward_shop.py
Purpose: Defines Flask routes and request-handling workflows for reward shop features.

Maintenance notes:
- Preserve tenant and family data isolation when changing queries.
- Keep route, template, and schema changes synchronized.
- Run regression tests before release packaging.
Documentation updated: 2026-07-31.
"""

from flask import Blueprint, abort, flash, redirect, render_template, url_for

from models.economy import get_balance
from models.rewards import create_reward_request, get_reward, get_reward_requests, get_shop_rewards
from models.users import get_user_by_id

reward_shop_blueprint = Blueprint("reward_shop", __name__, url_prefix="/child")


def _child_or_404(user_id: int):
    """Handle the child or 404 workflow."""
    child = get_user_by_id(user_id)
    if child is None or child["role"] != "child":
        abort(404)
    return child


@reward_shop_blueprint.route("/<int:user_id>/rewards")
def shop(user_id: int):
    """Handle the shop workflow."""
    child = _child_or_404(user_id)
    balance = get_balance(user_id)
    rewards = []
    for row in get_shop_rewards():
        item = dict(row)
        item["can_afford"] = balance >= int(row["cost"])
        item["stars_needed"] = max(0, int(row["cost"]) - balance)
        rewards.append(item)
    pending_ids = {
        row["reward_id"] for row in get_reward_requests(child_id=user_id, status="pending")
    }
    return render_template(
        "child/rewards/shop.html", child=child, balance=balance,
        rewards=rewards, pending_reward_ids=pending_ids,
    )


@reward_shop_blueprint.route("/<int:user_id>/rewards/<int:reward_id>")
def detail(user_id: int, reward_id: int):
    """Handle the detail workflow."""
    child = _child_or_404(user_id)
    reward = get_reward(reward_id)
    if reward is None or not reward["active"]:
        abort(404)
    balance = get_balance(user_id)
    pending = any(
        row["reward_id"] == reward_id
        for row in get_reward_requests(child_id=user_id, status="pending")
    )
    return render_template(
        "child/rewards/detail.html", child=child, reward=reward, balance=balance,
        stars_needed=max(0, int(reward["cost"]) - balance), pending=pending,
    )


@reward_shop_blueprint.route("/<int:user_id>/rewards/<int:reward_id>/request", methods=["POST"])
def request_reward(user_id: int, reward_id: int):
    """Handle the request reward workflow."""
    _child_or_404(user_id)
    success, message, _ = create_reward_request(user_id, reward_id)
    flash(message, "success" if success else "warning")
    return redirect(url_for("reward_shop.shop", user_id=user_id))


@reward_shop_blueprint.route("/<int:user_id>/reward-history")
def history(user_id: int):
    """Handle the history workflow."""
    child = _child_or_404(user_id)
    return render_template(
        "child/rewards/history.html", child=child,
        balance=get_balance(user_id), reward_requests=get_reward_requests(child_id=user_id),
    )
