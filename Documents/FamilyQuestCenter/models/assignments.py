"""Family Quest Center developer documentation.

File: models/assignments.py
Purpose: Provides database access and domain operations for assignments data.

Maintenance notes:
- Preserve tenant and family data isolation when changing queries.
- Keep route, template, and schema changes synchronized.
- Run regression tests before release packaging.
Documentation updated: 2026-07-31.
"""

from datetime import datetime

from database import get_db
from models.achievements import check_and_award_achievements
from models.economy import award_stars
from models.progression import calculate_level
from models.settings import get_xp_for_difficulty
from services.tenant_context import get_current_family_id


def get_active_children():
    """Return all active child profiles."""

    database = get_db()

    return database.execute(
        """
        SELECT
            id,
            name,
            initial,
            total_points,
            total_xp,
            current_level,
            current_streak
        FROM users
        WHERE role = 'child'
          AND active = 1
          AND family_id = ?
        ORDER BY name ASC
        """,
        (get_current_family_id(),),
    ).fetchall()


def get_active_chores():
    """Return all active quests available for assignment."""

    database = get_db()

    return database.execute(
        """
        SELECT
            id,
            title,
            description,
            difficulty,
            stars,
            approval_required
        FROM chores
        WHERE active = 1
          AND family_id = ?
        ORDER BY title ASC
        """,
        (get_current_family_id(),),
    ).fetchall()


def assignment_exists(chore_id: int, child_id: int, due_date: str):
    """Check whether the quest is already assigned to the child for the date."""

    database = get_db()

    assignment = database.execute(
        """
        SELECT id
        FROM assignments
        WHERE chore_id = ?
          AND child_id = ?
          AND due_date = ?
          AND status != 'cancelled'
          AND family_id = ?
        """,
        (chore_id, child_id, due_date, get_current_family_id()),
    ).fetchone()

    return assignment is not None


def create_assignment(
    chore_id: int,
    child_id: int,
    due_date: str,
    schedule_id: int | None = None,
) -> bool:
    """Assign a quest to a child and return whether it was created."""

    database = get_db()

    cursor = database.execute(
        """
        INSERT OR IGNORE INTO assignments (
            chore_id,
            child_id,
            schedule_id,
            due_date,
            status, family_id
        )
        VALUES (?, ?, ?, ?, 'assigned', ?)
        """,
        (chore_id, child_id, schedule_id, due_date, get_current_family_id()),
    )

    database.commit()
    return cursor.rowcount > 0


def get_assignments_for_date(due_date: str):
    """Return all assignments scheduled for a specific date."""

    database = get_db()

    return database.execute(
        """
        SELECT
            assignments.id,
            assignments.child_id,
            assignments.chore_id,
            assignments.due_date,
            assignments.status,
            chores.title,
            chores.stars,
            chores.difficulty,
            chores.approval_required,
            users.name AS child_name,
            CASE WHEN assignments.chain_instance_id IS NOT NULL THEN 'adventure' ELSE 'daily' END AS mission_type
        FROM assignments
        JOIN chores ON chores.id = assignments.chore_id
                   AND chores.family_id = assignments.family_id
        JOIN users ON users.id = assignments.child_id
                  AND users.family_id = assignments.family_id
        WHERE assignments.due_date = ?
          AND assignments.family_id = ?
          AND chores.active = 1
          AND users.active = 1
          AND assignments.status != 'cancelled'
        ORDER BY users.name ASC, chores.title ASC
        """,
        (due_date, get_current_family_id()),
    ).fetchall()


def get_child_assignments(child_id: int, due_date: str):
    """Return today's assignments for a child."""

    database = get_db()

    rows = database.execute(
        """
        SELECT
            assignments.id,
            assignments.status,
            assignments.completed_at,
            assignments.chain_instance_id,
            assignments.chain_step_id,
            chores.title,
            chores.description,
            chores.stars,
            chores.difficulty,
            chores.approval_required,
            CASE WHEN assignments.chain_instance_id IS NOT NULL THEN 'adventure' ELSE 'daily' END AS mission_type,
            quest_chains.name AS adventure_name,
            quest_chain_steps.step_order AS adventure_step_order,
            CASE WHEN assignments.chain_instance_id IS NOT NULL AND EXISTS (
                SELECT 1 FROM assignments prior_a
                JOIN quest_chain_steps prior_s ON prior_s.id=prior_a.chain_step_id
                JOIN chores prior_c ON prior_c.id=prior_a.chore_id
                WHERE prior_a.chain_instance_id=assignments.chain_instance_id
                  AND prior_s.step_order < quest_chain_steps.step_order
                  AND prior_c.active=1
                  AND prior_a.status NOT IN ('completed','approved','cancelled')
            ) THEN 1 ELSE 0 END AS is_locked
        FROM assignments
        JOIN chores ON chores.id = assignments.chore_id
        LEFT JOIN quest_chain_instances ON quest_chain_instances.id=assignments.chain_instance_id
        LEFT JOIN quest_chains ON quest_chains.id=quest_chain_instances.chain_id
        LEFT JOIN quest_chain_steps ON quest_chain_steps.id=assignments.chain_step_id
        WHERE assignments.child_id = ?
          AND assignments.due_date = ?
          AND assignments.family_id = ?
          AND chores.active = 1
          AND assignments.status != 'cancelled'
          AND (assignments.chain_instance_id IS NULL OR quest_chains.active=1)
        ORDER BY CASE WHEN assignments.chain_instance_id IS NULL THEN 0 ELSE 1 END,
                 COALESCE(quest_chains.name,''), COALESCE(quest_chain_steps.step_order,0), chores.title
        """,
        (child_id, due_date, get_current_family_id()),
    ).fetchall()
    return [dict(row, xp_reward=get_xp_for_difficulty(row["difficulty"])) for row in rows]


def complete_assignment(assignment_id: int) -> bool:
    """Mark an assigned quest as completed."""

    database = get_db()

    cursor = database.execute(
        """
        UPDATE assignments
        SET
            status = 'completed',
            completed_at = ?
        WHERE id = ?
          AND status = 'assigned'
          AND family_id = ?
        """,
        (datetime.now().isoformat(), assignment_id, get_current_family_id()),
    )

    database.commit()
    return cursor.rowcount == 1


def get_assignment(assignment_id: int):
    """Return a single assignment with reward information."""

    database = get_db()

    row = database.execute(
        """
        SELECT
            assignments.*,
            chores.title,
            chores.stars,
            chores.difficulty,
            chores.approval_required
        FROM assignments
        JOIN chores ON chores.id = assignments.chore_id
        WHERE assignments.id = ? AND assignments.family_id = ?
        """,
        (assignment_id, get_current_family_id()),
    ).fetchone()
    return None if row is None else dict(row, xp_reward=get_xp_for_difficulty(row["difficulty"]))


def _award_assignment(database, assignment) -> None:
    """Award stars and XP inside the caller's database transaction."""

    stars = int(assignment["stars"])
    xp = get_xp_for_difficulty(assignment["difficulty"])
    child_id = assignment["child_id"]
    assignment_id = assignment["id"]

    current_user = database.execute(
        """
        SELECT total_xp
        FROM users
        WHERE id = ?
        """,
        (child_id,),
    ).fetchone()

    new_total_xp = int(current_user["total_xp"] or 0) + xp
    new_level = calculate_level(new_total_xp)

    database.execute(
        """
        UPDATE users
        SET total_xp = ?, current_level = ?
        WHERE id = ?
        """,
        (new_total_xp, new_level, child_id),
    )

    reason = f"Quest completed: {assignment['title']}"
    award_stars(
        database, child_id, stars, reason,
        reference_type="ASSIGNMENT",
        reference_id=assignment_id,
        idempotency_key=f"quest:{assignment_id}",
    )

    database.execute(
        """
        INSERT OR IGNORE INTO point_history (
            child_id, assignment_id, points, reason
        ) VALUES (?, ?, ?, ?)
        """,
        (child_id, assignment_id, stars, reason),
    )

    database.execute(
        """
        INSERT INTO xp_history (
            child_id,
            assignment_id,
            xp,
            reason,
            family_id
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (child_id, assignment_id, xp, f"Quest completed: {assignment['title']}", get_current_family_id()),
    )


def complete_and_award_assignment(assignment_id: int) -> dict | None:
    """Complete a no-approval quest and award rewards exactly once."""

    database = get_db()

    assignment = database.execute(
        """
        SELECT
            assignments.id,
            assignments.child_id,
            assignments.status,
            chores.title,
            chores.stars,
            chores.difficulty,
            chores.approval_required
        FROM assignments
        JOIN chores ON chores.id = assignments.chore_id
        WHERE assignments.id = ? AND assignments.family_id = ?
        """,
        (assignment_id, get_current_family_id()),
    ).fetchone()

    if assignment is None:
        return False

    if assignment["status"] != "assigned" or assignment["approval_required"]:
        return False

    try:
        database.execute("BEGIN")

        cursor = database.execute(
            """
            UPDATE assignments
            SET
                status = 'approved',
                completed_at = ?,
                approved_at = ?
            WHERE id = ?
              AND status = 'assigned'
            """,
            (
                datetime.now().isoformat(),
                datetime.now().isoformat(),
                assignment_id,
            ),
        )

        if cursor.rowcount != 1:
            database.rollback()
            return False

        _award_assignment(database, assignment)
        from models.quest_chains import process_chain_completion
        chain_completed = process_chain_completion(database, assignment_id)
        from models.family_progression import calculate_streaks
        streaks = calculate_streaks(assignment["child_id"])
        database.execute(
            "UPDATE users SET current_streak = ? WHERE id = ?",
            (streaks["current"], assignment["child_id"]),
        )
        unlocked = check_and_award_achievements(database, assignment["child_id"])
        database.commit()
        return {"awarded": True, "achievements": unlocked, "chain_completed": chain_completed}
    except Exception:
        database.rollback()
        raise


def get_pending_approvals():
    """Return completed assignments waiting for approval for this family only."""
    database = get_db()
    family_id = get_current_family_id()
    rows = database.execute(
        """
        SELECT
            assignments.id,
            assignments.child_id,
            assignments.chore_id,
            assignments.completed_at,
            assignments.chain_instance_id,
            assignments.chain_step_id,
            chores.title,
            chores.description,
            chores.stars,
            chores.difficulty,
            users.name AS child_name
        FROM assignments
        JOIN chores ON chores.id = assignments.chore_id
                   AND chores.family_id = assignments.family_id
        JOIN users ON users.id = assignments.child_id
                  AND users.family_id = assignments.family_id
        WHERE assignments.status = 'completed'
          AND chores.approval_required = 1
          AND chores.active = 1
          AND users.active = 1
          AND assignments.family_id = ?
          AND chores.family_id = ?
          AND users.family_id = ?
        ORDER BY assignments.completed_at ASC
        """,
        (family_id, family_id, family_id),
    ).fetchall()
    return [dict(row, xp_reward=get_xp_for_difficulty(row["difficulty"])) for row in rows]

def reject_assignment(assignment_id: int):
    """Return a completed assignment to assigned status for this family only."""
    database = get_db()
    database.execute(
        """
        UPDATE assignments
        SET status = 'assigned', completed_at = NULL
        WHERE id = ? AND status = 'completed' AND family_id = ?
        """,
        (assignment_id, get_current_family_id()),
    )
    database.commit()

def approve_and_award_assignment(assignment_id: int) -> dict | None:
    """Approve a completed quest and award rewards exactly once."""

    database = get_db()

    assignment = database.execute(
        """
        SELECT
            assignments.id,
            assignments.child_id,
            assignments.status,
            chores.title,
            chores.stars,
            chores.difficulty,
            chores.approval_required
        FROM assignments
        JOIN chores ON chores.id = assignments.chore_id
        WHERE assignments.id = ? AND assignments.family_id = ?
        """,
        (assignment_id, get_current_family_id()),
    ).fetchone()

    if assignment is None or assignment["status"] != "completed":
        return False

    try:
        database.execute("BEGIN")

        cursor = database.execute(
            """
            UPDATE assignments
            SET
                status = 'approved',
                approved_at = ?
            WHERE id = ?
              AND status = 'completed'
            """,
            (datetime.now().isoformat(), assignment_id),
        )

        if cursor.rowcount != 1:
            database.rollback()
            return False

        _award_assignment(database, assignment)
        from models.quest_chains import process_chain_completion
        chain_completed = process_chain_completion(database, assignment_id)
        from models.family_progression import calculate_streaks
        streaks = calculate_streaks(assignment["child_id"])
        database.execute(
            "UPDATE users SET current_streak = ? WHERE id = ?",
            (streaks["current"], assignment["child_id"]),
        )
        unlocked = check_and_award_achievements(database, assignment["child_id"])
        database.commit()
        return {"awarded": True, "achievements": unlocked, "chain_completed": chain_completed}
    except Exception:
        database.rollback()
        raise


def count_assignments_for_date(due_date: str) -> int:
    """Count non-cancelled missions scheduled for a date for this family."""
    result = get_db().execute(
        """
        SELECT COUNT(*) AS assignment_count
        FROM assignments
        WHERE due_date = ? AND status != 'cancelled' AND family_id = ?
        """,
        (due_date, get_current_family_id()),
    ).fetchone()
    return result["assignment_count"]

def count_pending_approvals() -> int:
    """Count approval-required completed assignments for this family."""
    family_id = get_current_family_id()
    result = get_db().execute(
        """
        SELECT COUNT(*) AS approval_count
        FROM assignments
        JOIN chores ON chores.id = assignments.chore_id
        WHERE assignments.status = 'completed'
          AND chores.approval_required = 1
          AND assignments.family_id = ?
          AND chores.family_id = ?
        """,
        (family_id, family_id),
    ).fetchone()
    return result["approval_count"]

