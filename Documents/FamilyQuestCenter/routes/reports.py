"""Family Quest Center developer documentation.

File: routes/reports.py
Purpose: Defines Flask routes and request-handling workflows for reports features.
"""

from datetime import date, timedelta
from flask import Blueprint, render_template
from database import get_db
from services.tenant_context import get_current_family_id
from models.journeys import ensure_journey_tables
from models.dashboard import get_recent_activity

reports_blueprint = Blueprint("reports", __name__, url_prefix="/parent/reports")


@reports_blueprint.route("/")
def overview():
    """Render family-scoped progress reports."""
    ensure_journey_tables()
    db = get_db()
    family_id = get_current_family_id()
    today = date.today()
    week_start = (today - timedelta(days=6)).isoformat()
    month_start = today.replace(day=1).isoformat()

    child_rows = db.execute(
        """
        SELECT u.id, u.name, u.total_xp, u.total_points, u.current_level,
               COUNT(CASE WHEN a.status='approved' THEN 1 END) AS approved_quests,
               COUNT(CASE WHEN a.status='approved' AND date(a.approved_at) >= date(?) THEN 1 END) AS weekly_quests,
               COUNT(CASE WHEN a.status='approved' AND date(a.approved_at) >= date(?) THEN 1 END) AS monthly_quests
        FROM users u
        LEFT JOIN assignments a
          ON a.child_id=u.id AND a.family_id=u.family_id
        WHERE u.role='child' AND u.active=1 AND u.family_id=?
        GROUP BY u.id
        ORDER BY u.name
        """,
        (week_start, month_start, family_id),
    ).fetchall()

    children = []
    for row in child_rows:
        child = dict(row)
        adventure_counts = db.execute(
            """
            SELECT
              (SELECT COUNT(*) FROM quest_chain_instances
                 WHERE child_id=? AND family_id=? AND status='completed')
              +
              (SELECT COUNT(*) FROM adventure_instances_v2
                 WHERE child_id=? AND family_id=? AND status='completed') AS lifetime,
              (SELECT COUNT(*) FROM quest_chain_instances
                 WHERE child_id=? AND family_id=? AND status='completed'
                   AND completed_at IS NOT NULL AND date(completed_at) >= date(?))
              +
              (SELECT COUNT(*) FROM adventure_instances_v2
                 WHERE child_id=? AND family_id=? AND status='completed'
                   AND completed_at IS NOT NULL AND date(completed_at) >= date(?)) AS weekly,
              (SELECT COUNT(*) FROM quest_chain_instances
                 WHERE child_id=? AND family_id=? AND status='completed'
                   AND completed_at IS NOT NULL AND date(completed_at) >= date(?))
              +
              (SELECT COUNT(*) FROM adventure_instances_v2
                 WHERE child_id=? AND family_id=? AND status='completed'
                   AND completed_at IS NOT NULL AND date(completed_at) >= date(?)) AS monthly
            """,
            (
                child['id'], family_id, child['id'], family_id,
                child['id'], family_id, week_start, child['id'], family_id, week_start,
                child['id'], family_id, month_start, child['id'], family_id, month_start,
            ),
        ).fetchone()
        child['approved_adventures'] = int(adventure_counts['lifetime'] or 0)
        child['weekly_adventures'] = int(adventure_counts['weekly'] or 0)
        child['monthly_adventures'] = int(adventure_counts['monthly'] or 0)
        children.append(child)

    popular = db.execute(
        """
        SELECT c.title, COUNT(*) AS completions
        FROM assignments a
        JOIN chores c ON c.id=a.chore_id AND c.family_id=a.family_id
        WHERE a.status='approved' AND a.family_id=?
        GROUP BY c.id
        ORDER BY completions DESC, c.title
        LIMIT 5
        """,
        (family_id,),
    ).fetchall()

    quest_totals = db.execute(
        """
        SELECT
          COUNT(CASE WHEN status='approved' AND date(approved_at) >= date(?) THEN 1 END) weekly,
          COUNT(CASE WHEN status='approved' AND date(approved_at) >= date(?) THEN 1 END) monthly,
          COUNT(CASE WHEN status='completed' THEN 1 END) pending
        FROM assignments
        WHERE family_id=?
        """,
        (week_start, month_start, family_id),
    ).fetchone()
    adventure_totals = db.execute(
        """
        SELECT
          (SELECT COUNT(*) FROM quest_chain_instances WHERE family_id=? AND status='completed' AND completed_at IS NOT NULL AND date(completed_at) >= date(?))
          + (SELECT COUNT(*) FROM adventure_instances_v2 WHERE family_id=? AND status='completed' AND completed_at IS NOT NULL AND date(completed_at) >= date(?)) AS weekly,
          (SELECT COUNT(*) FROM quest_chain_instances WHERE family_id=? AND status='completed' AND completed_at IS NOT NULL AND date(completed_at) >= date(?))
          + (SELECT COUNT(*) FROM adventure_instances_v2 WHERE family_id=? AND status='completed' AND completed_at IS NOT NULL AND date(completed_at) >= date(?)) AS monthly,
          (SELECT COUNT(*) FROM quest_chain_instances WHERE family_id=? AND status='completed')
          + (SELECT COUNT(*) FROM adventure_instances_v2 WHERE family_id=? AND status='completed') AS lifetime
        """,
        (
            family_id, week_start, family_id, week_start,
            family_id, month_start, family_id, month_start,
            family_id, family_id,
        ),
    ).fetchone()
    totals = {
        'weekly': int(quest_totals['weekly'] or 0),
        'monthly': int(quest_totals['monthly'] or 0),
        'pending': int(quest_totals['pending'] or 0),
        'weekly_adventures': int(adventure_totals['weekly'] or 0),
        'monthly_adventures': int(adventure_totals['monthly'] or 0),
        'lifetime_adventures': int(adventure_totals['lifetime'] or 0),
    }

    return render_template(
        "parent/reports.html",
        children=children,
        popular=popular,
        totals=totals,
        recent_activity=get_recent_activity(limit=50),
    )
