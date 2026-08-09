"""Family Quest Center developer documentation.

File: assignment_generator.py
Purpose: Supports the assignment generator portion of Family Quest Center.

Maintenance notes:
- Preserve tenant and family data isolation when changing queries.
- Keep route, template, and schema changes synchronized.
- Run regression tests before release packaging.
Documentation updated: 2026-07-31.
"""

from datetime import date

from models.assignments import create_assignment
from models.recurring_missions import get_active_schedules_for_date


def generate_assignments_for_date(target_date: date | None = None) -> dict:
    """Generate all scheduled assignments for one date."""

    selected_date = target_date or date.today()
    due_date = selected_date.isoformat()

    created_count = 0
    skipped_count = 0

    for schedule in get_active_schedules_for_date(selected_date):
        created = create_assignment(
            chore_id=schedule["chore_id"],
            child_id=schedule["child_id"],
            due_date=due_date,
            schedule_id=schedule["id"],
        )

        if created:
            created_count += 1
        else:
            skipped_count += 1

    return {
        "date": due_date,
        "created": created_count,
        "skipped": skipped_count,
    }
