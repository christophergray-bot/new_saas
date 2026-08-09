"""Shared family challenge calculations with strict tenant isolation."""
from datetime import date

from database import get_db
from services.tenant_context import get_current_family_id

GOAL_TYPES = {
    "quests": "Quests completed",
    "xp": "XP earned",
    "stars": "Stars earned",
    "active_days": "Active family days",
}


def list_challenges(include_archived=False):
    """Handle the list challenges workflow."""
    db = get_db()
    family_id = get_current_family_id()
    where = "family_id=?" if include_archived else "family_id=? AND active=1"
    rows = db.execute(
        f"SELECT * FROM family_challenges WHERE {where} ORDER BY active DESC,end_date,name",
        (family_id,),
    ).fetchall()
    return [challenge_progress(dict(row)) for row in rows]


def create_challenge(name, description, goal_type, target, start_date, end_date, reward_text):
    """Create challenge."""
    db = get_db()
    cursor = db.execute(
        """INSERT INTO family_challenges
           (name,description,goal_type,target_value,start_date,end_date,reward_text,family_id)
           VALUES(?,?,?,?,?,?,?,?)""",
        (
            name,
            description,
            goal_type,
            target,
            start_date,
            end_date,
            reward_text,
            get_current_family_id(),
        ),
    )
    db.commit()
    return cursor.lastrowid


def set_challenge_active(challenge_id, active):
    """Handle the set challenge active workflow."""
    db = get_db()
    db.execute(
        "UPDATE family_challenges SET active=? WHERE id=? AND family_id=?",
        (1 if active else 0, challenge_id, get_current_family_id()),
    )
    db.commit()


def challenge_progress(challenge):
    """Handle the challenge progress workflow."""
    family_id = get_current_family_id()
    if int(challenge.get("family_id") or -1) != family_id:
        raise ValueError("Challenge does not belong to the current family.")

    db = get_db()
    start = challenge["start_date"]
    end = challenge["end_date"]
    goal_type = challenge["goal_type"]
    params = (start, end, family_id)

    if goal_type == "quests":
        value = db.execute(
            """SELECT COUNT(*) FROM assignments
               WHERE status='approved'
                 AND date(approved_at) BETWEEN ? AND ?
                 AND family_id=?""",
            params,
        ).fetchone()[0]
    elif goal_type == "xp":
        value = db.execute(
            """SELECT COALESCE(SUM(xp),0) FROM xp_history
               WHERE date(created_at) BETWEEN ? AND ? AND family_id=?""",
            params,
        ).fetchone()[0]
    elif goal_type == "stars":
        value = db.execute(
            """SELECT COALESCE(SUM(amount),0) FROM star_transactions
               WHERE amount>0 AND date(created_at) BETWEEN ? AND ? AND family_id=?""",
            params,
        ).fetchone()[0]
    else:
        value = db.execute(
            """SELECT COUNT(DISTINCT date(approved_at)) FROM assignments
               WHERE status='approved'
                 AND date(approved_at) BETWEEN ? AND ?
                 AND family_id=?""",
            params,
        ).fetchone()[0]

    challenge["current_value"] = int(value or 0)
    challenge["percent"] = min(
        100,
        round(challenge["current_value"] / max(1, int(challenge["target_value"])) * 100),
    )

    today = date.today().isoformat()
    challenge["display_status"] = (
        "completed"
        if challenge["current_value"] >= challenge["target_value"]
        else "ended"
        if today > challenge["end_date"]
        else "upcoming"
        if today < challenge["start_date"]
        else "active"
    )
    challenge["goal_label"] = GOAL_TYPES.get(
        goal_type, goal_type.replace("_", " ").title()
    )
    challenge["contributors"] = [
        dict(row)
        for row in db.execute(
            """SELECT u.name, COUNT(a.id) contribution
               FROM users u
               LEFT JOIN assignments a
                 ON a.child_id=u.id
                AND a.status='approved'
                AND date(a.approved_at) BETWEEN ? AND ?
                AND a.family_id=?
               WHERE u.role='child' AND u.active=1 AND u.family_id=?
               GROUP BY u.id
               ORDER BY contribution DESC,u.name""",
            (start, end, family_id, family_id),
        ).fetchall()
    ]
    return challenge
