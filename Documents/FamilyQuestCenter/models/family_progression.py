"""Family progression statistics, streaks, heat maps, and activity timelines."""
from collections import defaultdict
from datetime import date, datetime, timedelta

from database import get_db


def _approved_dates(child_id: int) -> list[date]:
    """Handle the approved dates workflow."""
    rows = get_db().execute(
        """
        SELECT DISTINCT due_date
        FROM assignments
        WHERE child_id = ? AND status = 'approved'
        ORDER BY due_date ASC
        """,
        (child_id,),
    ).fetchall()
    results = []
    for row in rows:
        try:
            results.append(date.fromisoformat(row["due_date"]))
        except (TypeError, ValueError):
            continue
    return results


def calculate_streaks(child_id: int, today: date | None = None) -> dict:
    """Return current and longest day streaks based on approved quest dates."""
    today = today or date.today()
    dates = _approved_dates(child_id)
    if not dates:
        return {"current": 0, "longest": 0, "last_active": None}

    longest = 1
    run = 1
    for previous, current in zip(dates, dates[1:]):
        if current == previous + timedelta(days=1):
            run += 1
            longest = max(longest, run)
        elif current != previous:
            run = 1

    date_set = set(dates)
    anchor = today if today in date_set else today - timedelta(days=1)
    current_streak = 0
    while anchor in date_set:
        current_streak += 1
        anchor -= timedelta(days=1)

    return {
        "current": current_streak,
        "longest": longest,
        "last_active": dates[-1].isoformat(),
    }


def refresh_streak(child_id: int) -> dict:
    """Handle the refresh streak workflow."""
    streaks = calculate_streaks(child_id)
    database = get_db()
    database.execute(
        "UPDATE users SET current_streak = ? WHERE id = ?",
        (streaks["current"], child_id),
    )
    database.commit()
    return streaks


def get_child_statistics(child_id: int) -> dict:
    """Retrieve child statistics."""
    database = get_db()
    totals = database.execute(
        """
        SELECT
            COUNT(*) AS assigned_count,
            SUM(CASE WHEN status = 'approved' THEN 1 ELSE 0 END) AS completed_count,
            SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS awaiting_count,
            SUM(CASE WHEN status = 'approved' THEN c.stars ELSE 0 END) AS quest_stars,
            SUM(CASE WHEN status = 'approved' THEN c.stars * 10 ELSE 0 END) AS quest_xp
        FROM assignments a
        JOIN chores c ON c.id = a.chore_id
        WHERE a.child_id = ?
        """,
        (child_id,),
    ).fetchone()

    favorite = database.execute(
        """
        SELECT c.title, COUNT(*) AS completions
        FROM assignments a
        JOIN chores c ON c.id = a.chore_id
        WHERE a.child_id = ? AND a.status = 'approved'
        GROUP BY c.id, c.title
        ORDER BY completions DESC, c.title ASC
        LIMIT 1
        """,
        (child_id,),
    ).fetchone()

    rewards = database.execute(
        """
        SELECT COUNT(*)
        FROM reward_requests
        WHERE child_id = ? AND status IN ('approved', 'redeemed')
        """,
        (child_id,),
    ).fetchone()[0]
    achievements = database.execute(
        "SELECT COUNT(*) FROM user_achievements WHERE user_id = ?",
        (child_id,),
    ).fetchone()[0]
    user = database.execute(
        "SELECT total_xp, total_points FROM users WHERE id = ?",
        (child_id,),
    ).fetchone()

    assigned = int(totals["assigned_count"] or 0)
    completed = int(totals["completed_count"] or 0)
    return {
        "assigned_count": assigned,
        "completed_count": completed,
        "awaiting_count": int(totals["awaiting_count"] or 0),
        "success_rate": round((completed / assigned) * 100) if assigned else 0,
        "quest_stars": int(totals["quest_stars"] or 0),
        "quest_xp": int(totals["quest_xp"] or 0),
        "lifetime_xp": int(user["total_xp"] or 0),
        "current_stars": int(user["total_points"] or 0),
        "favorite_quest": favorite["title"] if favorite else "No completed quests yet",
        "favorite_count": int(favorite["completions"]) if favorite else 0,
        "rewards_earned": int(rewards),
        "achievements_earned": int(achievements),
        "streaks": calculate_streaks(child_id),
    }


def get_activity_heatmap(child_id: int, days: int = 84) -> list[dict]:
    """Retrieve activity heatmap."""
    end = date.today()
    start = end - timedelta(days=days - 1)
    rows = get_db().execute(
        """
        SELECT due_date, COUNT(*) AS count
        FROM assignments
        WHERE child_id = ? AND status = 'approved' AND due_date BETWEEN ? AND ?
        GROUP BY due_date
        """,
        (child_id, start.isoformat(), end.isoformat()),
    ).fetchall()
    counts = {row["due_date"]: int(row["count"]) for row in rows}
    result = []
    for offset in range(days):
        day = start + timedelta(days=offset)
        count = counts.get(day.isoformat(), 0)
        intensity = 0 if count == 0 else min(count, 4)
        result.append({
            "date": day.isoformat(),
            "label": day.strftime("%b %d").replace(" 0", " ") if hasattr(day, 'strftime') else day.isoformat(),
            "count": count,
            "intensity": intensity,
        })
    return result


def get_child_timeline(child_id: int, limit: int = 40) -> list[dict]:
    """Retrieve child timeline."""
    database = get_db()
    events = []

    for row in database.execute(
        """
        SELECT a.approved_at AS occurred_at, c.title, c.stars
        FROM assignments a JOIN chores c ON c.id = a.chore_id
        WHERE a.child_id = ? AND a.status = 'approved' AND a.approved_at IS NOT NULL
        ORDER BY a.approved_at DESC LIMIT ?
        """,
        (child_id, limit),
    ).fetchall():
        events.append({"occurred_at": row["occurred_at"], "icon": "✅", "title": row["title"], "detail": f"Quest completed · +{row['stars']} stars · +{row['stars'] * 10} XP", "type": "quest"})

    for row in database.execute(
        """
        SELECT ua.earned_at AS occurred_at, a.icon, a.name, a.xp_reward, a.star_reward
        FROM user_achievements ua JOIN achievements a ON a.id = ua.achievement_id
        WHERE ua.user_id = ? ORDER BY ua.earned_at DESC LIMIT ?
        """,
        (child_id, limit),
    ).fetchall():
        rewards = []
        if row["xp_reward"]: rewards.append(f"+{row['xp_reward']} XP")
        if row["star_reward"]: rewards.append(f"+{row['star_reward']} stars")
        detail = "Achievement unlocked" + (" · " + " · ".join(rewards) if rewards else "")
        events.append({"occurred_at": row["occurred_at"], "icon": row["icon"], "title": row["name"], "detail": detail, "type": "achievement"})

    for row in database.execute(
        """
        SELECT rr.requested_at, rr.approved_at, rr.redeemed_at, rr.status, r.icon, r.name, r.cost
        FROM reward_requests rr JOIN rewards r ON r.id = rr.reward_id
        WHERE rr.child_id = ? AND rr.status IN ('approved','redeemed')
        ORDER BY COALESCE(rr.redeemed_at, rr.approved_at, rr.requested_at) DESC LIMIT ?
        """,
        (child_id, limit),
    ).fetchall():
        occurred = row["redeemed_at"] or row["approved_at"] or row["requested_at"]
        events.append({"occurred_at": occurred, "icon": row["icon"], "title": row["name"], "detail": f"Reward {row['status']} · {row['cost']} stars", "type": "reward"})

    events.sort(key=lambda item: item["occurred_at"] or "", reverse=True)
    return events[:limit]


def group_timeline_by_day(events: list[dict]) -> list[dict]:
    """Handle the group timeline by day workflow."""
    groups = defaultdict(list)
    for event in events:
        raw = event.get("occurred_at") or ""
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            key = parsed.date().isoformat()
            event["time_label"] = parsed.strftime("%I:%M %p").lstrip("0")
        except (TypeError, ValueError):
            key = raw[:10] or "Unknown"
            event["time_label"] = ""
        groups[key].append(event)
    output = []
    today = date.today()
    for key in sorted(groups.keys(), reverse=True):
        try:
            day = date.fromisoformat(key)
            if day == today: label = "Today"
            elif day == today - timedelta(days=1): label = "Yesterday"
            else: label = day.strftime("%B %d, %Y").replace(" 0", " ")
        except ValueError:
            label = key
        output.append({"date": key, "label": label, "events": groups[key]})
    return output
