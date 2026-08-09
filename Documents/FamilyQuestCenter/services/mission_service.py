"""Responsibility-system service for Quests and Missions.

Version 2 terminology:

* A Quest is a reusable responsibility stored in the Quest Library.
* A Mission is a Quest assigned to a child for a particular date.

The Version 1 database still stores both Missions and legacy Adventure steps in
``assignments``.  This service is the Responsibility-system boundary: every
read filters out Adventure-linked rows, and every write rejects them.  The
legacy Adventure workflow is isolated in ``services.adventure_service`` until
it is replaced by the Journey system.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from assignment_generator import generate_assignments_for_date
from models.assignments import (
    approve_and_award_assignment,
    complete_and_award_assignment,
    complete_assignment,
    get_active_children,
    get_active_chores,
    get_assignment,
    get_assignments_for_date,
    get_child_assignments,
    get_pending_approvals,
    reject_assignment,
)


def _is_mission(row) -> bool:
    """Return True only for Responsibility-system assignment rows."""

    return row is not None and row.get("chain_instance_id") is None


def generate_missions_for_date(target_date: date | None = None) -> dict[str, Any]:
    """Generate scheduled Missions for the selected date."""

    return generate_assignments_for_date(target_date)


def list_missions_for_date(due_date: str):
    """Return Responsibility Missions due on a date."""

    return [row for row in get_assignments_for_date(due_date) if row["mission_type"] != "adventure"]


def list_child_missions(child_id: int, due_date: str):
    """Return a child's Responsibility Missions due on a date."""

    return [row for row in get_child_assignments(child_id, due_date) if row["mission_type"] != "adventure"]


def get_mission(mission_id: int):
    """Return one Responsibility Mission, never an Adventure step."""

    row = get_assignment(mission_id)
    return row if _is_mission(row) else None


def submit_mission_for_approval(mission_id: int) -> bool:
    """Submit an approval-required Mission for parent review."""

    if get_mission(mission_id) is None:
        return False
    return complete_assignment(mission_id)


def complete_mission(mission_id: int) -> dict[str, Any] | bool | None:
    """Complete and reward a Mission that does not require approval."""

    if get_mission(mission_id) is None:
        return False
    return complete_and_award_assignment(mission_id)


def list_pending_mission_approvals():
    """Return Responsibility Missions waiting for parent approval."""

    return [row for row in get_pending_approvals() if row.get("chain_instance_id") is None]


def approve_mission(mission_id: int) -> dict[str, Any] | bool | None:
    """Approve a submitted Mission and award XP and Stars once."""

    if get_mission(mission_id) is None:
        return False
    return approve_and_award_assignment(mission_id)


def return_mission(mission_id: int) -> bool:
    """Return a submitted Mission to the child for additional work."""

    if get_mission(mission_id) is None:
        return False
    reject_assignment(mission_id)
    return True


def count_missions_for_date(due_date: str) -> int:
    """Count Responsibility Missions due on a date."""

    return len(list_missions_for_date(due_date))


def count_pending_mission_approvals() -> int:
    """Count Responsibility Missions waiting for parent approval."""

    return len(list_pending_mission_approvals())


def list_active_children():
    """Return active children available for Mission scheduling."""

    return get_active_children()


def list_active_quests():
    """Return active Quests available for Mission scheduling."""

    return get_active_chores()
