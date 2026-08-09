"""Achievement engine for Family Quest Center."""

from __future__ import annotations

from datetime import datetime

from database import get_db
from models.progression import calculate_level
from models.economy import award_stars
from services.tenant_context import get_current_family_id



def ensure_family_achievement_tables() -> None:
    """Handle the ensure family achievement tables workflow."""
    database = get_db()
    columns = {row['name'] for row in database.execute('PRAGMA table_info(achievements)').fetchall()}
    if 'is_system' not in columns:
        database.execute('ALTER TABLE achievements ADD COLUMN is_system INTEGER NOT NULL DEFAULT 1')
    if 'series_key' not in columns:
        database.execute('ALTER TABLE achievements ADD COLUMN series_key TEXT')
    if 'tier' not in columns:
        database.execute('ALTER TABLE achievements ADD COLUMN tier INTEGER NOT NULL DEFAULT 1')

    user_achievement_columns = {
        row['name'] for row in database.execute('PRAGMA table_info(user_achievements)').fetchall()
    }
    if 'notified_at' not in user_achievement_columns:
        database.execute('ALTER TABLE user_achievements ADD COLUMN notified_at TEXT')
        database.execute(
            "UPDATE user_achievements SET notified_at = earned_at WHERE notified_at IS NULL"
        )

    database.executescript(
        """
        CREATE TABLE IF NOT EXISTS family_achievements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            family_id INTEGER NOT NULL,
            achievement_id INTEGER NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(family_id, achievement_id),
            FOREIGN KEY(achievement_id) REFERENCES achievements(id)
        );
        CREATE INDEX IF NOT EXISTS idx_family_achievements_family
            ON family_achievements(family_id, active);
        """
    )
    database.commit()


def _child_family_id(database, child_id: int) -> int | None:
    """Handle the child family id workflow."""
    row = database.execute("SELECT family_id FROM users WHERE id=? AND role='child'", (child_id,)).fetchone()
    return None if row is None else int(row['family_id'])


REQUIREMENT_LABELS = {
    "QUESTS_COMPLETED": "Approved quests completed",
    "STARS_EARNED": "Lifetime stars earned",
    "TOTAL_XP": "Total XP earned",
    "LEVEL": "Current level reached",
    "CURRENT_STREAK": "Current daily streak",
    "ADVENTURES_COMPLETED": "Completed Adventures",
}

SUPPORTED_REQUIREMENTS = set(REQUIREMENT_LABELS)


def _get_child_metrics(database, child_id: int) -> dict:
    """Return current lifetime statistics used by achievement rules."""

    user = database.execute(
        """
        SELECT total_xp, current_level, current_streak
        FROM users
        WHERE id = ?
          AND role = 'child'
        """,
        (child_id,),
    ).fetchone()

    if user is None:
        return {}

    quest_count = database.execute(
        """
        SELECT COUNT(*) AS value
        FROM assignments
        WHERE child_id = ?
          AND status = 'approved'
        """,
        (child_id,),
    ).fetchone()["value"]

    stars_earned = database.execute(
        """
        SELECT COALESCE(SUM(points), 0) AS value
        FROM point_history
        WHERE child_id = ?
          AND points > 0
        """,
        (child_id,),
    ).fetchone()["value"]

    adventure_count = 0
    table_exists = database.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='adventure_instances_v2'"
    ).fetchone()
    if table_exists:
        adventure_count = database.execute(
            "SELECT COUNT(*) AS value FROM adventure_instances_v2 WHERE child_id=? AND status='completed'",
            (child_id,),
        ).fetchone()["value"]

    return {
        "QUESTS_COMPLETED": int(quest_count or 0),
        "STARS_EARNED": int(stars_earned or 0),
        "TOTAL_XP": int(user["total_xp"] or 0),
        "LEVEL": int(user["current_level"] or 1),
        "CURRENT_STREAK": int(user["current_streak"] or 0),
        "ADVENTURES_COMPLETED": int(adventure_count or 0),
    }


def _award_achievement_reward(database, child_id: int, achievement) -> None:
    """Apply achievement XP or star rewards within an open transaction."""

    xp_reward = int(achievement["xp_reward"] or 0)
    star_reward = int(achievement["star_reward"] or 0)
    reason = f"Achievement unlocked: {achievement['name']}"

    if star_reward:
        award_stars(
            database, child_id, star_reward, reason,
            reference_type="ACHIEVEMENT",
            reference_id=achievement["id"],
            idempotency_key=f"achievement:{child_id}:{achievement['id']}",
        )

        database.execute(
            """
            INSERT INTO point_history (child_id, assignment_id, points, reason)
            VALUES (?, NULL, ?, ?)
            """,
            (child_id, star_reward, reason),
        )

    if xp_reward:
        user = database.execute(
            """
            SELECT total_xp
            FROM users
            WHERE id = ?
            """,
            (child_id,),
        ).fetchone()

        new_total_xp = int(user["total_xp"] or 0) + xp_reward

        database.execute(
            """
            UPDATE users
            SET
                total_xp = ?,
                current_level = ?
            WHERE id = ?
            """,
            (new_total_xp, calculate_level(new_total_xp), child_id),
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
            VALUES (?, NULL, ?, ?, ?)
            """,
            (child_id, xp_reward, reason, get_current_family_id()),
        )


def check_and_award_achievements(database, child_id: int) -> list[dict]:
    """Unlock every currently eligible achievement exactly once.

    The caller must already have an open transaction. The function repeats the
    check because an XP reward can raise the child to another achievement.
    """

    ensure_family_achievement_tables()
    unlocked: list[dict] = []

    while True:
        metrics = _get_child_metrics(database, child_id)
        if not metrics:
            break

        achievements = database.execute(
            """
            SELECT
                achievements.id,
                achievements.name,
                achievements.description,
                achievements.icon,
                achievements.category,
                achievements.requirement_type,
                achievements.requirement_value,
                achievements.xp_reward,
                achievements.star_reward
            FROM achievements
            LEFT JOIN user_achievements
                ON user_achievements.achievement_id = achievements.id
               AND user_achievements.user_id = ?
            WHERE achievements.active = 1
              AND (
                    achievements.is_system = 1
                    OR EXISTS (
                        SELECT 1 FROM family_achievements fa
                        WHERE fa.achievement_id = achievements.id
                          AND fa.family_id = ?
                          AND fa.active = 1
                    )
              )
              AND user_achievements.id IS NULL
              AND (
                    achievements.series_key IS NULL
                    OR achievements.tier = (
                        SELECT MIN(next_a.tier)
                        FROM achievements next_a
                        LEFT JOIN user_achievements next_ua
                          ON next_ua.achievement_id=next_a.id AND next_ua.user_id=?
                        WHERE next_a.active=1
                          AND next_a.series_key=achievements.series_key
                          AND next_ua.id IS NULL
                    )
              )
            ORDER BY achievements.requirement_value, achievements.id
            """,
            (child_id, _child_family_id(database, child_id), child_id),
        ).fetchall()

        newly_unlocked = []

        for achievement in achievements:
            requirement_type = achievement["requirement_type"]
            if requirement_type not in SUPPORTED_REQUIREMENTS:
                continue

            current_value = metrics.get(requirement_type, 0)
            requirement_value = int(achievement["requirement_value"] or 0)

            if current_value < requirement_value:
                continue

            cursor = database.execute(
                """
                INSERT OR IGNORE INTO user_achievements (
                    user_id,
                    achievement_id,
                    earned_at
                )
                VALUES (?, ?, ?)
                """,
                (child_id, achievement["id"], datetime.now().isoformat()),
            )

            if cursor.rowcount != 1:
                continue

            _award_achievement_reward(database, child_id, achievement)

            achievement_info = {
                "id": achievement["id"],
                "name": achievement["name"],
                "description": achievement["description"],
                "icon": achievement["icon"],
                "xp_reward": int(achievement["xp_reward"] or 0),
                "star_reward": int(achievement["star_reward"] or 0),
            }
            newly_unlocked.append(achievement_info)
            unlocked.append(achievement_info)

        if not newly_unlocked:
            break

    return unlocked


def mark_achievement_notifications_seen(child_id: int, achievement_ids: list[int]) -> None:
    """Mark achievement popups delivered during an active child workflow."""
    if not achievement_ids:
        return
    database = get_db()
    ensure_family_achievement_tables()
    placeholders = ",".join("?" for _ in achievement_ids)
    database.execute(
        f"UPDATE user_achievements SET notified_at=COALESCE(notified_at, ?) "
        f"WHERE user_id=? AND achievement_id IN ({placeholders})",
        (datetime.now().isoformat(), child_id, *achievement_ids),
    )
    database.commit()


def pop_pending_achievement_notifications(child_id: int) -> list[dict]:
    """Return unseen child achievements once, then mark them delivered."""
    database = get_db()
    ensure_family_achievement_tables()
    rows = database.execute(
        """
        SELECT achievements.id, achievements.name, achievements.description,
               achievements.icon, achievements.xp_reward, achievements.star_reward
        FROM user_achievements
        JOIN achievements ON achievements.id=user_achievements.achievement_id
        WHERE user_achievements.user_id=? AND user_achievements.notified_at IS NULL
        ORDER BY datetime(user_achievements.earned_at), user_achievements.id
        """,
        (child_id,),
    ).fetchall()
    pending=[dict(row) for row in rows]
    if pending:
        ids=[row['id'] for row in pending]
        placeholders=','.join('?' for _ in ids)
        database.execute(
            f"UPDATE user_achievements SET notified_at=? WHERE user_id=? "
            f"AND achievement_id IN ({placeholders}) AND notified_at IS NULL",
            (datetime.now().isoformat(), child_id, *ids),
        )
        database.commit()
    return pending


def get_child_achievements(child_id: int) -> list[dict]:
    """Return earned and locked achievements with current progress."""

    database = get_db()
    ensure_family_achievement_tables()
    metrics = _get_child_metrics(database, child_id)

    rows = database.execute(
        """
        SELECT
            achievements.id,
            achievements.name,
            achievements.description,
            achievements.icon,
            achievements.category,
            achievements.requirement_type,
            achievements.requirement_value,
            achievements.xp_reward,
            achievements.star_reward,
            achievements.hidden,
            user_achievements.earned_at
        FROM achievements
        LEFT JOIN user_achievements
            ON user_achievements.achievement_id = achievements.id
           AND user_achievements.user_id = ?
        WHERE achievements.active = 1
          AND (
                achievements.is_system = 1
                OR EXISTS (
                    SELECT 1 FROM family_achievements fa
                    WHERE fa.achievement_id = achievements.id
                      AND fa.family_id = ?
                      AND fa.active = 1
                )
          )
          AND (
                user_achievements.id IS NOT NULL
                OR achievements.hidden = 0
                OR achievements.tier = (
                    SELECT MIN(next_a.tier)
                    FROM achievements next_a
                    LEFT JOIN user_achievements next_ua
                      ON next_ua.achievement_id=next_a.id AND next_ua.user_id=?
                    WHERE next_a.active=1
                      AND next_a.series_key=achievements.series_key
                      AND next_ua.id IS NULL
                )
          )
        ORDER BY
            CASE WHEN user_achievements.id IS NOT NULL THEN 0 ELSE 1 END,
            achievements.category,
            achievements.requirement_value,
            achievements.id
        """,
        (child_id, _child_family_id(database, child_id), child_id),
    ).fetchall()

    results = []
    for row in rows:
        current_value = int(metrics.get(row["requirement_type"], 0))
        target = int(row["requirement_value"] or 0)
        progress_percent = 100 if target <= 0 else min(100, int(current_value * 100 / target))

        results.append(
            {
                "id": row["id"],
                "name": row["name"],
                "description": row["description"],
                "icon": row["icon"],
                "category": row["category"],
                "requirement_type": row["requirement_type"],
                "requirement_value": target,
                "xp_reward": int(row["xp_reward"] or 0),
                "star_reward": int(row["star_reward"] or 0),
                "earned_at": row["earned_at"],
                "earned": row["earned_at"] is not None,
                "current_value": current_value,
                "progress_percent": progress_percent,
            }
        )

    return results


def get_achievement_summary(child_id: int) -> dict:
    """Return compact achievement counts for the child dashboard."""

    database = get_db()
    ensure_family_achievement_tables()

    family_id = _child_family_id(database, child_id)
    visible_total = len(get_child_achievements(child_id))

    earned = database.execute(
        """
        SELECT COUNT(*) AS value
        FROM user_achievements
        JOIN achievements ON achievements.id = user_achievements.achievement_id
        WHERE user_achievements.user_id = ?
          AND achievements.active = 1
        """,
        (child_id,),
    ).fetchone()["value"]

    recent = database.execute(
        """
        SELECT achievements.name, achievements.icon, user_achievements.earned_at
        FROM user_achievements
        JOIN achievements ON achievements.id = user_achievements.achievement_id
        WHERE user_achievements.user_id = ?
        ORDER BY user_achievements.earned_at DESC
        LIMIT 1
        """,
        (child_id,),
    ).fetchone()

    return {
        "earned": int(earned or 0),
        "total": int(visible_total),
        "recent": recent,
    }


def get_achievement_admin_list(search: str = "", status: str = "all", requirement: str = "all"):
    """Return current-family achievements, including effective archive status."""
    database = get_db()
    ensure_family_achievement_tables()
    family_id = get_current_family_id()
    clauses = ["a.is_system=1"]
    params = [family_id]
    if search:
        clauses.append("(LOWER(a.name) LIKE ? OR LOWER(a.description) LIKE ? OR LOWER(a.category) LIKE ?)")
        term = f"%{search.lower()}%"
        params.extend([term, term, term])
    effective_active = "CASE WHEN fa.id IS NOT NULL THEN fa.active ELSE a.active END"
    if status == "active":
        clauses.append(f"{effective_active} = 1")
    elif status == "inactive":
        clauses.append(f"{effective_active} = 0")
    if requirement in SUPPORTED_REQUIREMENTS:
        clauses.append("a.requirement_type = ?")
        params.append(requirement)
    where = "WHERE " + " AND ".join(clauses)
    return database.execute(
        f"""
        SELECT a.*, {effective_active} AS effective_active,
               {effective_active} AS active, COUNT(ua.id) AS earned_count
        FROM achievements a
        LEFT JOIN family_achievements fa
          ON fa.achievement_id=a.id AND fa.family_id=?
        LEFT JOIN user_achievements ua ON ua.achievement_id=a.id
        {where}
        GROUP BY a.id
        ORDER BY effective_active DESC, a.category COLLATE NOCASE,
                 a.requirement_value, a.name COLLATE NOCASE
        """,
        params,
    ).fetchall()


def get_achievement(achievement_id: int):
    """Retrieve achievement."""
    ensure_family_achievement_tables()
    family_id = get_current_family_id()
    return get_db().execute(
        """SELECT a.* FROM achievements a WHERE a.id=? AND
           (a.is_system=1 OR EXISTS (SELECT 1 FROM family_achievements fa
             WHERE fa.achievement_id=a.id AND fa.family_id=?))""",
        (achievement_id, family_id),
    ).fetchone()


def create_achievement(*, name: str, description: str, icon: str, category: str,
                       requirement_type: str, requirement_value: int, xp_reward: int,
                       star_reward: int, hidden: bool):
    """Create achievement."""
    ensure_family_achievement_tables()
    database = get_db()
    family_id = get_current_family_id()
    with database:
        achievement_id = database.execute(
            """INSERT INTO achievements (name,description,icon,category,requirement_type,
                   requirement_value,xp_reward,star_reward,hidden,active,is_system)
               VALUES (?,?,?,?,?,?,?,?,?,1,0)""",
            (name,description,icon,category,requirement_type,requirement_value,
             xp_reward,star_reward,int(hidden)),
        ).lastrowid
        database.execute(
            "INSERT INTO family_achievements(family_id,achievement_id,active) VALUES(?,?,1)",
            (family_id, achievement_id),
        )
        return achievement_id


def update_achievement(achievement_id: int, *, name: str, description: str, icon: str,
                       category: str, requirement_type: str, requirement_value: int,
                       xp_reward: int, star_reward: int, hidden: bool):
    """Update achievement."""
    database = get_db()
    with database:
        database.execute(
            """
            UPDATE achievements
            SET name = ?, description = ?, icon = ?, category = ?, requirement_type = ?,
                requirement_value = ?, xp_reward = ?, star_reward = ?, hidden = ?
            WHERE id = ?
            """,
            (name, description, icon, category, requirement_type, requirement_value,
             xp_reward, star_reward, int(hidden), achievement_id),
        )


def set_achievement_active(achievement_id: int, active: bool):
    """Handle the set achievement active workflow."""
    ensure_family_achievement_tables()
    database = get_db()
    family_id = get_current_family_id()
    with database:
        mapping = database.execute(
            "SELECT id FROM family_achievements WHERE family_id=? AND achievement_id=?",
            (family_id, achievement_id),
        ).fetchone()
        if mapping:
            database.execute(
                "UPDATE family_achievements SET active=? WHERE id=?",
                (int(active), mapping['id']),
            )
        else:
            database.execute("UPDATE achievements SET active=? WHERE id=? AND is_system=1", (int(active), achievement_id))
