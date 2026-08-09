"""Family Quest Center developer documentation.

File: models/recurring_missions.py
Purpose: Provides database access and domain operations for recurring missions data.

Maintenance notes:
- Preserve tenant and family data isolation when changing queries.
- Keep route, template, and schema changes synchronized.
- Run regression tests before release packaging.
Documentation updated: 2026-07-31.
"""

from datetime import date
from typing import Iterable

from database import get_db
from services.tenant_context import get_current_family_id


VALID_SCHEDULE_TYPES = {"daily", "weekly", "monthly", "custom"}
VALID_WEEKDAYS = set(range(7))


def ensure_schedule_lifecycle_columns() -> None:
    """Keep Quest schedule lifecycle fields available on upgraded databases."""

    database = get_db()
    columns = {
        row["name"]
        for row in database.execute("PRAGMA table_info(quest_schedules)").fetchall()
    }

    status_column_added = "assignment_status" not in columns
    if status_column_added:
        database.execute(
            "ALTER TABLE quest_schedules ADD COLUMN assignment_status TEXT NOT NULL DEFAULT 'active'"
        )
    if "unassigned_at" not in columns:
        database.execute(
            "ALTER TABLE quest_schedules ADD COLUMN unassigned_at TEXT"
        )

    if status_column_added:
        database.execute(
            """UPDATE quest_schedules
               SET assignment_status = CASE WHEN active = 1 THEN 'active' ELSE 'paused' END"""
        )
    else:
        database.execute(
            """UPDATE quest_schedules
               SET assignment_status = CASE WHEN active = 1 THEN 'active' ELSE 'paused' END
               WHERE assignment_status IS NULL OR assignment_status = ''"""
        )
    database.commit()


def normalize_days_of_week(days: Iterable[int] | None) -> str | None:
    """Convert weekday values into a sorted comma-separated database value."""

    if not days:
        return None

    normalized = sorted({int(day) for day in days})

    if any(day not in VALID_WEEKDAYS for day in normalized):
        raise ValueError("Weekdays must be between 0 and 6.")

    return ",".join(str(day) for day in normalized)


def parse_days_of_week(value: str | None) -> set[int]:
    """Convert a stored comma-separated weekday value into a set."""

    if not value:
        return set()

    return {
        int(day)
        for day in value.split(",")
        if day.strip() != ""
    }


def validate_schedule(
    schedule_type: str,
    days_of_week: Iterable[int] | None = None,
    day_of_month: int | None = None,
) -> tuple[str | None, int | None]:
    """Validate schedule-specific fields and return normalized values."""

    if schedule_type not in VALID_SCHEDULE_TYPES:
        raise ValueError("Select a valid schedule type.")

    normalized_days = normalize_days_of_week(days_of_week)

    if schedule_type == "daily":
        return None, None

    if schedule_type == "weekly":
        if not normalized_days:
            raise ValueError("Select one weekday for a weekly schedule.")

        selected_days = parse_days_of_week(normalized_days)

        if len(selected_days) != 1:
            raise ValueError("Weekly schedules require exactly one weekday.")

        return normalized_days, None

    if schedule_type == "custom":
        if not normalized_days:
            raise ValueError(
                "Select at least one weekday for a custom schedule."
            )

        return normalized_days, None

    if day_of_month is None or not 1 <= int(day_of_month) <= 28:
        raise ValueError(
            "Monthly schedules require a day from 1 through 28."
        )

    return None, int(day_of_month)


def create_schedule(
    chore_id: int,
    child_id: int,
    schedule_type: str,
    start_date: str,
    days_of_week: Iterable[int] | None = None,
    day_of_month: int | None = None,
    end_date: str | None = None,
) -> int:
    """Create a reusable quest schedule and return its ID."""

    normalized_days, normalized_month_day = validate_schedule(
        schedule_type,
        days_of_week,
        day_of_month,
    )

    if end_date and end_date < start_date:
        raise ValueError("The end date cannot be before the start date.")

    ensure_schedule_lifecycle_columns()
    database = get_db()

    cursor = database.execute(
        """
        INSERT INTO quest_schedules (
            chore_id,
            child_id,
            schedule_type,
            days_of_week,
            day_of_month,
            start_date,
            end_date,
            active,
            assignment_status,
            family_id
        )
        SELECT ?, ?, ?, ?, ?, ?, ?, 1, 'active', ?
        WHERE EXISTS (
            SELECT 1 FROM chores
            WHERE id = ? AND family_id = ? AND active = 1
        )
          AND EXISTS (
            SELECT 1 FROM users
            WHERE id = ? AND family_id = ? AND role = 'child' AND active = 1
        )
        """,
        (
            chore_id,
            child_id,
            schedule_type,
            normalized_days,
            normalized_month_day,
            start_date,
            end_date,
            get_current_family_id(),
            chore_id,
            get_current_family_id(),
            child_id,
            get_current_family_id(),
        ),
    )

    if cursor.rowcount != 1:
        database.rollback()
        raise ValueError("The selected child or quest does not belong to this family.")

    database.commit()
    return cursor.lastrowid


def update_schedule(
    schedule_id: int,
    chore_id: int,
    child_id: int,
    schedule_type: str,
    start_date: str,
    days_of_week: Iterable[int] | None = None,
    day_of_month: int | None = None,
    end_date: str | None = None,
) -> bool:
    """Update an existing quest schedule."""

    normalized_days, normalized_month_day = validate_schedule(
        schedule_type,
        days_of_week,
        day_of_month,
    )

    if end_date and end_date < start_date:
        raise ValueError("The end date cannot be before the start date.")

    ensure_schedule_lifecycle_columns()
    database = get_db()

    cursor = database.execute(
        """
        UPDATE quest_schedules
        SET
            chore_id = ?,
            child_id = ?,
            schedule_type = ?,
            days_of_week = ?,
            day_of_month = ?,
            start_date = ?,
            end_date = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
          AND family_id = ?
          AND EXISTS (SELECT 1 FROM chores WHERE id = ? AND family_id = ?)
          AND EXISTS (SELECT 1 FROM users WHERE id = ? AND family_id = ? AND role = 'child')
          AND assignment_status != 'unassigned'
        """,
        (
            chore_id,
            child_id,
            schedule_type,
            normalized_days,
            normalized_month_day,
            start_date,
            end_date,
            schedule_id,
            get_current_family_id(),
            chore_id,
            get_current_family_id(),
            child_id,
            get_current_family_id(),
        ),
    )

    database.commit()
    return cursor.rowcount > 0


def get_schedule(schedule_id: int):
    """Return one schedule with its child and quest information."""

    ensure_schedule_lifecycle_columns()
    database = get_db()

    return database.execute(
        """
        SELECT
            quest_schedules.*,
            chores.title,
            chores.description,
            chores.stars,
            users.name AS child_name
        FROM quest_schedules
        JOIN chores
            ON chores.id = quest_schedules.chore_id
        JOIN users
            ON users.id = quest_schedules.child_id
        WHERE quest_schedules.id = ?
          AND quest_schedules.family_id = ?
          AND chores.family_id = quest_schedules.family_id
          AND users.family_id = quest_schedules.family_id
        """,
        (schedule_id, get_current_family_id()),
    ).fetchone()


def get_schedules(include_inactive: bool = True):
    """Return quest schedules for the parent schedule page."""

    ensure_schedule_lifecycle_columns()
    database = get_db()
    active_filter = "" if include_inactive else (
        "AND quest_schedules.active = 1"
    )

    return database.execute(
        f"""
        SELECT
            quest_schedules.*,
            chores.title,
            chores.description,
            chores.stars,
            users.name AS child_name
        FROM quest_schedules
        JOIN chores
            ON chores.id = quest_schedules.chore_id
        JOIN users
            ON users.id = quest_schedules.child_id
        WHERE quest_schedules.family_id = ?
          AND chores.family_id = quest_schedules.family_id
          AND users.family_id = quest_schedules.family_id
        {active_filter}
        ORDER BY
            quest_schedules.active DESC,
            users.name ASC,
            chores.title ASC
        """,
        (get_current_family_id(),),
    ).fetchall()


def get_active_schedule_summaries_by_chore() -> dict[int, list[dict]]:
    """Return current Quest assignment summaries grouped by Quest ID."""

    ensure_schedule_lifecycle_columns()
    rows = get_db().execute(
        """
        SELECT
            qs.id AS schedule_id,
            qs.chore_id,
            qs.schedule_type,
            qs.days_of_week,
            qs.day_of_month,
            qs.start_date,
            qs.end_date,
            qs.active,
            qs.assignment_status,
            u.name AS child_name
        FROM quest_schedules qs
        JOIN chores c
            ON c.id = qs.chore_id
           AND c.family_id = qs.family_id
        JOIN users u
            ON u.id = qs.child_id
           AND u.family_id = qs.family_id
        WHERE qs.family_id = ?
          AND qs.assignment_status != 'unassigned'
          AND c.active = 1
          AND u.active = 1
        ORDER BY c.title COLLATE NOCASE, u.name COLLATE NOCASE, qs.id
        """,
        (get_current_family_id(),),
    ).fetchall()

    summaries: dict[int, list[dict]] = {}
    for row in rows:
        summaries.setdefault(row["chore_id"], []).append(dict(row))
    return summaries


def set_schedule_active(schedule_id: int, active: bool) -> bool:
    """Activate or pause a Quest schedule that has not been unassigned."""

    ensure_schedule_lifecycle_columns()
    database = get_db()

    cursor = database.execute(
        """
        UPDATE quest_schedules
        SET
            active = ?,
            assignment_status = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
          AND family_id = ?
          AND assignment_status != 'unassigned' 
        """,
        (
            1 if active else 0,
            'active' if active else 'paused',
            schedule_id,
            get_current_family_id(),
        ),
    )

    database.commit()
    return cursor.rowcount > 0


def unassign_schedule(schedule_id: int) -> bool:
    """Stop future Quest generation while preserving all existing history."""

    ensure_schedule_lifecycle_columns()
    database = get_db()
    cursor = database.execute(
        """
        UPDATE quest_schedules
        SET active = 0,
            assignment_status = 'unassigned',
            unassigned_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
          AND family_id = ?
          AND assignment_status != 'unassigned'
        """,
        (schedule_id, get_current_family_id()),
    )
    database.commit()
    return cursor.rowcount > 0


def schedule_applies_on(schedule, target_date: date) -> bool:
    """Return True when a schedule should create an assignment on a date."""

    target_iso = target_date.isoformat()

    if not schedule["active"]:
        return False

    if target_iso < schedule["start_date"]:
        return False

    if schedule["end_date"] and target_iso > schedule["end_date"]:
        return False

    schedule_type = schedule["schedule_type"]

    if schedule_type == "daily":
        return True

    if schedule_type in {"weekly", "custom"}:
        weekdays = parse_days_of_week(schedule["days_of_week"])
        return target_date.weekday() in weekdays

    if schedule_type == "monthly":
        return target_date.day == schedule["day_of_month"]

    return False


def get_active_schedules_for_date(target_date: date):
    """Return active schedules whose date range includes the target date."""

    database = get_db()
    target_iso = target_date.isoformat()

    schedules = database.execute(
        """
        SELECT
            quest_schedules.*
        FROM quest_schedules
        JOIN chores
            ON chores.id = quest_schedules.chore_id
        JOIN users
            ON users.id = quest_schedules.child_id
        WHERE quest_schedules.active = 1
          AND quest_schedules.family_id = ?
          AND chores.family_id = quest_schedules.family_id
          AND users.family_id = quest_schedules.family_id
          AND chores.active = 1
          AND users.active = 1
          AND quest_schedules.start_date <= ?
          AND (
                quest_schedules.end_date IS NULL
                OR quest_schedules.end_date >= ?
          )
        ORDER BY quest_schedules.id ASC
        """,
        (
            get_current_family_id(),
            target_iso,
            target_iso,
        ),
    ).fetchall()

    return [
        schedule
        for schedule in schedules
        if schedule_applies_on(schedule, target_date)
    ]
