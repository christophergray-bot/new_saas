"""Temporary boundary for the Version 1 Adventure implementation.

Adventure steps still live in the shared ``assignments`` table.  Keeping their
workflow here prevents the Version 2 Mission service from knowing about chain
instances or chain steps.  Sprint 2 can replace this module with the permanent
Adventure/Journey model without changing Responsibility routes.
"""

from __future__ import annotations

from typing import Any

from models.assignments import (
    approve_and_award_assignment,
    complete_and_award_assignment,
    complete_assignment,
    get_assignment,
    get_pending_approvals,
    reject_assignment,
)
from models.quest_chains import can_complete_chain_assignment


def _is_journey_assignment(row) -> bool:
    """Handle the is journey assignment workflow."""
    return row is not None and row.get("chain_instance_id") is not None


def get_journey_assignment(assignment_id: int):
    """Return a legacy Adventure-step assignment only."""

    row = get_assignment(assignment_id)
    return row if _is_journey_assignment(row) else None


def can_complete_journey(assignment_id: int):
    """Enforce ordered Adventure steps during the transition."""

    if get_journey_assignment(assignment_id) is None:
        return False, "Journey not found."
    return can_complete_chain_assignment(assignment_id)


def submit_journey_for_approval(assignment_id: int) -> bool:
    """Handle the submit journey for approval workflow."""
    if get_journey_assignment(assignment_id) is None:
        return False
    return complete_assignment(assignment_id)


def complete_journey(assignment_id: int) -> dict[str, Any] | bool | None:
    """Handle the complete journey workflow."""
    if get_journey_assignment(assignment_id) is None:
        return False
    return complete_and_award_assignment(assignment_id)


def list_pending_journey_approvals():
    """Handle the list pending journey approvals workflow."""
    return [row for row in get_pending_approvals() if row.get("chain_instance_id") is not None]


def approve_journey(assignment_id: int) -> dict[str, Any] | bool | None:
    """Handle the approve journey workflow."""
    if get_journey_assignment(assignment_id) is None:
        return False
    return approve_and_award_assignment(assignment_id)


def return_journey(assignment_id: int) -> bool:
    """Handle the return journey workflow."""
    if get_journey_assignment(assignment_id) is None:
        return False
    reject_assignment(assignment_id)
    return True


def count_pending_journey_approvals() -> int:
    """Handle the count pending journey approvals workflow."""
    return len(list_pending_journey_approvals())
