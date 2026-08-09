-- Family Quest Center Developer Notes
-- File: migrations/add_achievements.sql
-- Purpose: Defines database schema or migration operations for add achievements.
-- Maintenance: Back up data and test migrations against a copy before production use.
-- Documentation updated: 2026-07-31

CREATE TABLE IF NOT EXISTS achievements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL,
    icon TEXT NOT NULL DEFAULT '🏆',
    category TEXT NOT NULL,
    requirement_type TEXT NOT NULL,
    requirement_value INTEGER NOT NULL CHECK (requirement_value >= 0),
    xp_reward INTEGER NOT NULL DEFAULT 0 CHECK (xp_reward >= 0),
    star_reward INTEGER NOT NULL DEFAULT 0 CHECK (star_reward >= 0),
    hidden INTEGER NOT NULL DEFAULT 0 CHECK (hidden IN (0, 1)),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    is_system INTEGER NOT NULL DEFAULT 1,
    series_key TEXT,
    tier INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS user_achievements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    achievement_id INTEGER NOT NULL,
    earned_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    notified_at TEXT,

    FOREIGN KEY(user_id) REFERENCES users(id),
    FOREIGN KEY(achievement_id) REFERENCES achievements(id),

    UNIQUE(user_id, achievement_id)
);

CREATE INDEX IF NOT EXISTS user_achievements_user_index
ON user_achievements (user_id, earned_at);

-- Progressive built-in achievements are installed by services/default_achievements.py.
