"""Family Quest Center developer documentation.

File: models/users.py
Purpose: Provides database access and domain operations for users data.

Maintenance notes:
- Preserve tenant and family data isolation when changing queries.
- Keep route, template, and schema changes synchronized.
- Run regression tests before release packaging.
Documentation updated: 2026-07-31.
"""

from database import get_db
from services.tenant_context import get_current_family_id

USER_FIELDS = """
    id, name, role, initial, total_points, total_xp, current_level,
    current_streak, avatar_key, title_key, frame_key, theme_key
"""


def get_all_active_users():
    """Retrieve all active users."""
    return get_db().execute(
        f"SELECT {USER_FIELDS} FROM users WHERE active=1 AND family_id=? "
        "ORDER BY CASE role WHEN 'parent' THEN 0 ELSE 1 END,id",
        (get_current_family_id(),),
    ).fetchall()


def get_user_by_id(user_id: int):
    """Retrieve user by id."""
    return get_db().execute(
        f"SELECT {USER_FIELDS} FROM users WHERE id=? AND active=1 AND family_id=?",
        (user_id, get_current_family_id()),
    ).fetchone()


def get_children(include_inactive: bool = False):
    """Retrieve children for the current family.

    Active children are returned by default so assignment and day-to-day
    workflows cannot accidentally offer archived child profiles. Administrative
    screens that intentionally need archived children may opt in with
    ``include_inactive=True``.
    """
    active_clause = "" if include_inactive else " AND active=1"
    return get_db().execute(
        f"SELECT {USER_FIELDS},active FROM users "
        f"WHERE role='child' AND family_id=?{active_clause} "
        "ORDER BY active DESC,name",
        (get_current_family_id(),),
    ).fetchall()


def get_child(child_id: int):
    """Retrieve child."""
    return get_db().execute(
        f"SELECT {USER_FIELDS},active FROM users WHERE id=? AND role='child' AND family_id=?",
        (child_id, get_current_family_id()),
    ).fetchone()


def set_child_active(child_id: int, active: bool):
    """Handle the set child active workflow."""
    db=get_db(); db.execute(
        "UPDATE users SET active=? WHERE id=? AND role='child' AND family_id=?",
        (1 if active else 0, child_id, get_current_family_id()),
    ); db.commit()


def update_child(child_id: int, name: str, initial: str):
    """Update child."""
    db=get_db(); db.execute(
        "UPDATE users SET name=?,initial=? WHERE id=? AND role='child' AND family_id=?",
        (name, initial, child_id, get_current_family_id()),
    ); db.commit()


def create_child(name: str, initial: str) -> int:
    """Create a child profile and return its identifier."""
    db = get_db()
    cursor = db.execute(
        """INSERT INTO users(name,role,initial,active,total_points,total_xp,
        current_level,current_streak,avatar_key,title_key,frame_key,theme_key,family_id)
        VALUES(?,'child',?,1,0,0,1,0,'adventurer','adventurer','bronze','quest',?)""",
        (name, initial, get_current_family_id()),
    )
    db.commit()
    return int(cursor.lastrowid)


def get_child_details(child_id: int) -> dict | None:
    """Return complete, tenant-scoped parent-facing details for one child."""
    child = get_child(child_id)
    if child is None:
        return None

    db = get_db()
    family_id = get_current_family_id()

    assignments = db.execute(
        """SELECT a.id,a.due_date,a.status,a.completed_at,a.approved_at,
                  c.title,c.description,c.stars,c.difficulty
           FROM assignments a
           JOIN chores c ON c.id=a.chore_id AND c.family_id=a.family_id
           WHERE a.child_id=? AND a.family_id=?
           ORDER BY COALESCE(a.due_date,a.completed_at,a.approved_at) DESC,a.id DESC
           LIMIT 25""",
        (child_id, family_id),
    ).fetchall()

    adventures = db.execute(
        """SELECT ai.id,av.name,av.description,ai.status,ai.start_date,
                  ai.completed_at,ai.pending_approval
           FROM adventure_instances_v2 ai
           JOIN adventures_v2 av
             ON av.id=ai.adventure_id AND av.family_id=ai.family_id
           WHERE ai.child_id=? AND ai.family_id=?
           ORDER BY COALESCE(ai.completed_at,ai.start_date,ai.created_at) DESC,ai.id DESC
           LIMIT 25""",
        (child_id, family_id),
    ).fetchall()

    rewards = db.execute(
        """SELECT rr.id,r.name,r.icon,r.cost,rr.status,rr.requested_at,
                  rr.approved_at,rr.denied_at,rr.redeemed_at
           FROM reward_requests rr
           JOIN rewards r ON r.id=rr.reward_id AND r.family_id=rr.family_id
           WHERE rr.child_id=? AND rr.family_id=?
           ORDER BY COALESCE(rr.redeemed_at,rr.approved_at,rr.denied_at,rr.requested_at) DESC
           LIMIT 25""",
        (child_id, family_id),
    ).fetchall()

    achievements = db.execute(
        """SELECT a.id,a.name,a.description,a.icon,a.category,
                  a.xp_reward,a.star_reward,ua.earned_at
           FROM user_achievements ua
           JOIN achievements a ON a.id=ua.achievement_id
           WHERE ua.user_id=? AND ua.family_id=?
           ORDER BY ua.earned_at DESC,a.id DESC""",
        (child_id, family_id),
    ).fetchall()

    statistics = db.execute(
        """SELECT
             (SELECT COUNT(*) FROM assignments
                WHERE child_id=? AND family_id=?) AS assignments_total,
             (SELECT COUNT(*) FROM assignments
                WHERE child_id=? AND family_id=? AND status='approved') AS quests_completed,
             (
               (SELECT COUNT(*) FROM adventure_instances_v2
                  WHERE child_id=? AND family_id=? AND status='completed')
               +
               (SELECT COUNT(*) FROM quest_chain_instances
                  WHERE child_id=? AND family_id=? AND status='completed')
             ) AS adventures_completed,
             (SELECT COUNT(*) FROM reward_requests
                WHERE child_id=? AND family_id=?
                  AND status IN ('approved','redeemed')) AS rewards_earned,
             (SELECT COUNT(*) FROM user_achievements
                WHERE user_id=? AND family_id=?) AS achievements_earned""",
        (
            child_id, family_id,
            child_id, family_id,
            child_id, family_id,
            child_id, family_id,
            child_id, family_id,
            child_id, family_id,
        ),
    ).fetchone()

    return {
        "child": child,
        "assignments": assignments,
        "adventures": adventures,
        "rewards": rewards,
        "achievements": achievements,
        "statistics": dict(statistics),
    }
