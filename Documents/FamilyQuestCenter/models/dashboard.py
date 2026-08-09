"""Parent dashboard queries.

RC1.6.3 keeps dashboard presentation queries separate from assignment,
approval, and adventure workflow code. The functions in this module are read-only.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from database import get_db
from services.mission_service import list_pending_mission_approvals
from services.adventure_service import list_pending_journey_approvals
from models.journeys import list_pending_v2_journey_approvals, list_pending_adventure_approvals
from services.tenant_context import get_current_family_id


def _format_activity_time(value: str | None) -> str:
    """Return a compact, readable local timestamp for dashboard cards."""
    if not value:
        return "Time unavailable"

    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        try:
            parsed = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return value

    now = datetime.now(parsed.tzinfo) if parsed.tzinfo else datetime.now()
    clock_time = parsed.strftime("%I:%M %p").lstrip("0")
    month_day = f"{parsed.strftime('%b')} {parsed.day}"
    if parsed.date() == now.date():
        return f"Today at {clock_time}"
    if parsed.date().year == now.date().year:
        return f"{month_day} at {clock_time}"
    return f"{month_day}, {parsed.year}"


def get_dashboard_pending_approvals(limit: int = 5) -> list[dict]:
    """Return the oldest pending approvals first, prepared for display."""
    approvals = ([{**dict(r), "activity_kind": "mission"} for r in list_pending_mission_approvals()] +
                 [{**dict(r), "activity_kind": "legacy_journey"} for r in list_pending_journey_approvals()] +
                 list_pending_v2_journey_approvals() +
                 list_pending_adventure_approvals())
    approvals.sort(key=lambda row: row.get("completed_at") or "")
    approvals = approvals[:limit]
    return [
        {
            **assignment,
            "display_time": _format_activity_time(assignment.get("completed_at")),
        }
        for assignment in approvals
    ]


def get_recent_activity(limit: int = 10) -> list[dict]:
    """Return recent activity for the current family only."""
    database = get_db()
    family_id = get_current_family_id()
    rows = database.execute(
        """
        SELECT activity_type, child_name, title, action_label, type_label,
               reward_text, occurred_at
        FROM (
            SELECT 'quest_completed' activity_type, users.name child_name,
                   chores.title title, 'Completed a mission' action_label,
                   CASE WHEN assignments.chain_instance_id IS NOT NULL
                        THEN 'Adventure Mission' ELSE 'Daily Mission' END type_label,
                   NULL reward_text, assignments.completed_at occurred_at
            FROM assignments
            JOIN chores ON chores.id=assignments.chore_id
            JOIN users ON users.id=assignments.child_id
            WHERE assignments.completed_at IS NOT NULL
              AND assignments.family_id=? AND chores.family_id=? AND users.family_id=?

            UNION ALL

            SELECT 'quest_approved', users.name, chores.title, 'Mission approved',
                   CASE WHEN assignments.chain_instance_id IS NOT NULL
                        THEN 'Adventure Mission' ELSE 'Daily Mission' END,
                   '+' || chores.stars || ' Stars', assignments.approved_at
            FROM assignments
            JOIN chores ON chores.id=assignments.chore_id
            JOIN users ON users.id=assignments.child_id
            WHERE assignments.approved_at IS NOT NULL
              AND assignments.family_id=? AND chores.family_id=? AND users.family_id=?

            UNION ALL

            SELECT 'xp_awarded', users.name,
                   COALESCE(xp_history.reason,'Experience awarded'),
                   'Earned experience', 'Progress',
                   '+' || xp_history.xp || ' XP', xp_history.created_at
            FROM xp_history JOIN users ON users.id=xp_history.child_id
            WHERE users.family_id=?

            UNION ALL

            SELECT 'achievement_unlocked', users.name, achievements.name,
                   'Achievement unlocked', achievements.category,
                   CASE
                     WHEN achievements.xp_reward>0 AND achievements.star_reward>0
                     THEN '+' || achievements.xp_reward || ' XP · +' || achievements.star_reward || ' Stars'
                     WHEN achievements.xp_reward>0 THEN '+' || achievements.xp_reward || ' XP'
                     WHEN achievements.star_reward>0 THEN '+' || achievements.star_reward || ' Stars'
                     ELSE NULL END,
                   user_achievements.earned_at
            FROM user_achievements
            JOIN achievements ON achievements.id=user_achievements.achievement_id
            JOIN users ON users.id=user_achievements.user_id
            WHERE user_achievements.family_id=? AND users.family_id=?

            UNION ALL

            SELECT 'adventure_assigned', users.name, quest_chains.name,
                   'Started an adventure', 'Adventure', NULL,
                   quest_chain_instances.started_at
            FROM quest_chain_instances
            JOIN quest_chains ON quest_chains.id=quest_chain_instances.chain_id
            JOIN users ON users.id=quest_chain_instances.child_id
            WHERE quest_chain_instances.family_id=?
              AND quest_chains.family_id=? AND users.family_id=?

            UNION ALL

            SELECT 'adventure_completed', users.name, quest_chains.name,
                   'Adventure completed', 'Adventure', NULL,
                   quest_chain_instances.completed_at
            FROM quest_chain_instances
            JOIN quest_chains ON quest_chains.id=quest_chain_instances.chain_id
            JOIN users ON users.id=quest_chain_instances.child_id
            WHERE quest_chain_instances.completed_at IS NOT NULL
              AND quest_chain_instances.family_id=?
              AND quest_chains.family_id=? AND users.family_id=?

            UNION ALL

            SELECT 'adventure_assigned_v2', users.name, adventures_v2.name,
                   'Started an adventure', 'Adventure', NULL,
                   adventure_instances_v2.created_at
            FROM adventure_instances_v2
            JOIN adventures_v2 ON adventures_v2.id=adventure_instances_v2.adventure_id
            JOIN users ON users.id=adventure_instances_v2.child_id
            WHERE adventure_instances_v2.family_id=?
              AND adventures_v2.family_id=? AND users.family_id=?

            UNION ALL

            SELECT 'adventure_completed_v2', users.name, adventures_v2.name,
                   'Adventure completed', 'Adventure', NULL,
                   adventure_instances_v2.completed_at
            FROM adventure_instances_v2
            JOIN adventures_v2 ON adventures_v2.id=adventure_instances_v2.adventure_id
            JOIN users ON users.id=adventure_instances_v2.child_id
            WHERE adventure_instances_v2.completed_at IS NOT NULL
              AND adventure_instances_v2.family_id=?
              AND adventures_v2.family_id=? AND users.family_id=?

            UNION ALL

            SELECT 'reward_requested', users.name, rewards.name,
                   CASE reward_requests.status
                     WHEN 'approved' THEN 'Reward approved'
                     WHEN 'redeemed' THEN 'Reward redeemed'
                     WHEN 'denied' THEN 'Reward request declined'
                     ELSE 'Reward requested' END,
                   'Reward', rewards.cost || ' Stars',
                   COALESCE(reward_requests.redeemed_at,
                            reward_requests.approved_at,
                            reward_requests.denied_at,
                            reward_requests.requested_at)
            FROM reward_requests
            JOIN rewards ON rewards.id=reward_requests.reward_id
            JOIN users ON users.id=reward_requests.child_id
            WHERE reward_requests.family_id=?
              AND rewards.family_id=? AND users.family_id=?

            UNION ALL

            SELECT audit_log.action,
                   'Family' AS child_name,
                   COALESCE(audit_log.details, 'Child') AS title,
                   CASE audit_log.action
                     WHEN 'child_created' THEN 'Child profile created'
                     WHEN 'child_archived' THEN 'Child profile archived'
                     WHEN 'child_restored' THEN 'Child profile restored'
                   END AS action_label,
                   'Family Member' AS type_label,
                   NULL AS reward_text,
                   audit_log.created_at AS occurred_at
            FROM audit_log
            WHERE audit_log.family_id=?
              AND audit_log.action IN (
                  'child_created','child_archived','child_restored'
              )
        ) activity
        WHERE occurred_at IS NOT NULL
        ORDER BY datetime(occurred_at) DESC, occurred_at DESC
        LIMIT ?
        """,
        (
            family_id, family_id, family_id,
            family_id, family_id, family_id,
            family_id,
            family_id, family_id,
            family_id, family_id, family_id,
            family_id, family_id, family_id,
            family_id, family_id, family_id,
            family_id, family_id, family_id,
            family_id, family_id, family_id,
            family_id,
            limit,
        ),
    ).fetchall()

    icons = {
        "quest_completed": "✅",
        "quest_approved": "⭐",
        "xp_awarded": "✨",
        "achievement_unlocked": "🏆",
        "adventure_assigned": "🗺️",
        "adventure_completed": "🏁",
        "adventure_assigned_v2": "🗺️",
        "adventure_completed_v2": "🏁",
        "reward_requested": "🎁",
        "child_created": "👦",
        "child_archived": "📦",
        "child_restored": "♻️",
    }
    return [
        {
            **dict(row),
            "icon": icons.get(row["activity_type"], "•"),
            "display_time": _format_activity_time(row["occurred_at"]),
        }
        for row in rows
    ]

def get_weekly_family_stats() -> dict:
    """Return current-family totals for the current Monday-through-Sunday week."""
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=7)
    start_value = week_start.isoformat()
    end_value = week_end.isoformat()
    family_id = get_current_family_id()
    database = get_db()

    xp_row = database.execute(
        """SELECT COALESCE(SUM(xp_history.xp),0) total
           FROM xp_history
           JOIN users ON users.id=xp_history.child_id
           WHERE date(xp_history.created_at)>=date(?)
             AND date(xp_history.created_at)<date(?)
             AND users.family_id=?""",
        (start_value,end_value,family_id),
    ).fetchone()
    quests_row = database.execute(
        """SELECT COUNT(*) total FROM assignments
           WHERE status='approved' AND approved_at IS NOT NULL
             AND date(approved_at)>=date(?) AND date(approved_at)<date(?)
             AND family_id=?""",
        (start_value,end_value,family_id),
    ).fetchone()
    legacy_adventures_row = database.execute(
        """SELECT COUNT(*) total FROM quest_chain_instances
           WHERE status='completed' AND completed_at IS NOT NULL
             AND date(completed_at)>=date(?) AND date(completed_at)<date(?)
             AND family_id=?""",
        (start_value,end_value,family_id),
    ).fetchone()
    current_adventures_row = database.execute(
        """SELECT COUNT(*) total FROM adventure_instances_v2
           WHERE status='completed' AND completed_at IS NOT NULL
             AND date(completed_at)>=date(?) AND date(completed_at)<date(?)
             AND family_id=?""",
        (start_value,end_value,family_id),
    ).fetchone()
    streak_row = database.execute(
        """SELECT COALESCE(MAX(current_streak),0) total FROM users
           WHERE role='child' AND active=1 AND family_id=?""",
        (family_id,),
    ).fetchone()
    return {
        "xp_earned": int(xp_row["total"] or 0),
        "quests_completed": int(quests_row["total"] or 0),
        "adventures_completed": (
            int(legacy_adventures_row["total"] or 0)
            + int(current_adventures_row["total"] or 0)
        ),
        "longest_streak": int(streak_row["total"] or 0),
        "week_label": f"{week_start.strftime('%b')} {week_start.day}–{(week_end - timedelta(days=1)).strftime('%b')} {(week_end - timedelta(days=1)).day}",
    }

def count_active_adventures() -> int:
    """Return active current Adventure instances for the current family."""
    from models.journeys import ensure_journey_tables
    ensure_journey_tables()
    row = get_db().execute(
        """
        SELECT COUNT(*) total
        FROM adventure_instances_v2 ai
        JOIN adventures_v2 a ON a.id=ai.adventure_id AND a.family_id=ai.family_id
        JOIN users u ON u.id=ai.child_id AND u.family_id=ai.family_id
        WHERE ai.status='active'
          AND ai.family_id=?
          AND a.active=1
          AND u.active=1
        """,
        (get_current_family_id(),),
    ).fetchone()
    return int(row["total"] or 0)


def get_active_adventures(limit: int = 6) -> list[dict]:
    """Return active current Adventures for the current family."""
    from models.journeys import ensure_journey_tables
    ensure_journey_tables()
    database = get_db()
    family_id = get_current_family_id()
    rows = database.execute(
        """
        SELECT ai.id, ai.status, ai.start_date AS started_at, a.name,
               u.name AS child_name, COUNT(ji.id) AS total_steps,
               SUM(CASE WHEN ji.status='completed' THEN 1 ELSE 0 END) AS progressed_steps
        FROM adventure_instances_v2 ai
        JOIN adventures_v2 a ON a.id=ai.adventure_id AND a.family_id=ai.family_id
        JOIN users u ON u.id=ai.child_id AND u.family_id=ai.family_id
        LEFT JOIN journey_instances ji ON ji.adventure_instance_id=ai.id
        WHERE ai.status='active' AND ai.family_id=? AND a.active=1 AND u.active=1
        GROUP BY ai.id
        ORDER BY datetime(ai.created_at) DESC, ai.id DESC
        LIMIT ?
        """,
        (family_id, limit),
    ).fetchall()
    adventures=[]
    for row in rows:
        item=dict(row)
        total=int(item.get("total_steps") or 0)
        progressed=int(item.get("progressed_steps") or 0)
        percent=round((progressed/total)*100) if total else 0
        item.update(completed_steps=progressed, percent=max(0,min(100,percent)),
                    display_status="Not Started" if progressed==0 else "In Progress",
                    status_key="not-started" if progressed==0 else "in-progress")
        adventures.append(item)
    return adventures
