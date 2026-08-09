"""Built-in progressive achievement definitions and safe upgrade helpers."""
from __future__ import annotations

from contextlib import closing

import sqlite3
from pathlib import Path


def _series(prefix, description_template, icon, category, requirement_type, targets, *, xp_reward=0, star_reward=0):
    rows=[]
    for tier,target in enumerate(targets, start=1):
        name = prefix if len(targets) == 1 else f"{prefix}: {target}"
        rows.append({
            "name": name,
            "description": description_template.format(target=target),
            "icon": icon,
            "category": category,
            "requirement_type": requirement_type,
            "requirement_value": target,
            "xp_reward": xp_reward,
            "star_reward": star_reward,
            "series_key": requirement_type.lower(),
            "tier": tier,
        })
    return rows


CORE_ACHIEVEMENTS = [
    {
        "name": "First Steps",
        "description": "Complete your first approved Quest.",
        "icon": "👣",
        "category": "Getting Started",
        "requirement_type": "QUESTS_COMPLETED",
        "requirement_value": 1,
        "xp_reward": 25,
        "star_reward": 5,
        "series_key": "first_steps",
        "tier": 1,
    },
    *_series("Streak", "Build a {target}-day Quest streak.", "🔥", "Consistency", "CURRENT_STREAK", [3, 6, 12, 24, 48, 96, 192, 384], xp_reward=25),
    *_series("Level", "Reach Level {target}.", "🏅", "Growth", "LEVEL", [1, 2, 4, 8, 16, 32, 64], star_reward=10),
    *_series("Star Collector", "Earn {target} lifetime stars.", "⭐", "Collection", "STARS_EARNED", list(range(50, 2001, 50)), xp_reward=10),
    *_series("XP Explorer", "Earn {target} lifetime XP.", "✨", "Growth", "TOTAL_XP", [100, 200, 400, 800, 1600, 3200, 6400, 12800], star_reward=10),
    *_series("Quest Champion", "Complete {target} approved Quests.", "✅", "Questing", "QUESTS_COMPLETED", [5, 10, 20, 40, 80, 160, 320], xp_reward=25),
    *_series("Adventure Explorer", "Complete {target} Adventure" + ("" if False else "s") + ".", "🗺️", "Adventures", "ADVENTURES_COMPLETED", [1, 2, 4, 8, 16, 32, 64], xp_reward=40, star_reward=10),
]

# Correct singular wording for the first Adventure tier.
for item in CORE_ACHIEVEMENTS:
    if item["requirement_type"] == "ADVENTURES_COMPLETED" and item["requirement_value"] == 1:
        item["description"] = "Complete your first Adventure."


def ensure_core_achievements(database_path: str | Path) -> int:
    """Install and maintain the non-editable progressive achievement catalog."""
    path=Path(database_path)
    if not path.exists():
        return 0
    with closing(sqlite3.connect(path)) as db, db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='achievements'").fetchone():
            return 0
        columns={row[1] for row in db.execute("PRAGMA table_info(achievements)")}
        additions={
            "is_system": "INTEGER NOT NULL DEFAULT 1",
            "series_key": "TEXT",
            "tier": "INTEGER NOT NULL DEFAULT 1",
        }
        for name,definition in additions.items():
            if name not in columns:
                db.execute(f"ALTER TABLE achievements ADD COLUMN {name} {definition}")

        # Achievements are now fully system-controlled. Retire prior defaults and
        # family-created rules while preserving every child's historical unlocks.
        db.execute("UPDATE achievements SET active=0")
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='family_achievements'").fetchone():
            db.execute("UPDATE family_achievements SET active=0")

        for item in CORE_ACHIEVEMENTS:
            db.execute(
                """
                INSERT INTO achievements
                    (name,description,icon,category,requirement_type,requirement_value,
                     xp_reward,star_reward,hidden,active,is_system,series_key,tier)
                VALUES (?,?,?,?,?,?,?,?,1,1,1,?,?)
                ON CONFLICT(name) DO UPDATE SET
                    description=excluded.description,
                    icon=excluded.icon,
                    category=excluded.category,
                    requirement_type=excluded.requirement_type,
                    requirement_value=excluded.requirement_value,
                    xp_reward=excluded.xp_reward,
                    star_reward=excluded.star_reward,
                    hidden=1,
                    active=1,
                    is_system=1,
                    series_key=excluded.series_key,
                    tier=excluded.tier
                """,
                (item["name"],item["description"],item["icon"],item["category"],
                 item["requirement_type"],item["requirement_value"],item["xp_reward"],
                 item["star_reward"],item["series_key"],item["tier"]),
            )
        db.execute("CREATE INDEX IF NOT EXISTS idx_achievements_series ON achievements(series_key,tier,active)")
    return len(CORE_ACHIEVEMENTS)


def ensure_outdoor_achievements(database_path: str | Path) -> int:
    """Backward-compatible alias retained for older scripts."""
    return ensure_core_achievements(database_path)
