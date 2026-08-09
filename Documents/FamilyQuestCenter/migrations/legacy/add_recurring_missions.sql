-- Family Quest Center Developer Notes
-- File: migrations/legacy/add_recurring_missions.sql
-- Purpose: Defines database schema or migration operations for add recurring missions.
-- Maintenance: Back up data and test migrations against a copy before production use.
-- Documentation updated: 2026-07-31

CREATE TABLE IF NOT EXISTS recurring_missions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    chore_id INTEGER NOT NULL,
    child_id INTEGER NOT NULL,

    frequency TEXT NOT NULL
        CHECK (
            frequency IN (
                'daily',
                'weekly',
                'monthly'
            )
        ),

    weekday INTEGER,
    month_day INTEGER,

    start_date TEXT NOT NULL,
    end_date TEXT,

    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY(chore_id)
        REFERENCES chores(id),

    FOREIGN KEY(child_id)
        REFERENCES users(id),

    CHECK (
        weekday IS NULL
        OR weekday BETWEEN 0 AND 6
    ),

    CHECK (
        month_day IS NULL
        OR month_day BETWEEN 1 AND 28
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS assignments_unique_daily
ON assignments (
    chore_id,
    child_id,
    due_date
);