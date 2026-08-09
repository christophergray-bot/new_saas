-- Family Quest Center Developer Notes
-- File: migrations/legacy/add_quest_schedules.sql
-- Purpose: Defines database schema or migration operations for add quest schedules.
-- Maintenance: Back up data and test migrations against a copy before production use.
-- Documentation updated: 2026-07-31

PRAGMA foreign_keys = OFF;

CREATE TABLE IF NOT EXISTS quest_schedules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chore_id INTEGER NOT NULL,
    child_id INTEGER NOT NULL,

    schedule_type TEXT NOT NULL
        CHECK (
            schedule_type IN (
                'daily',
                'weekly',
                'monthly',
                'custom'
            )
        ),

    days_of_week TEXT,
    day_of_month INTEGER,

    start_date TEXT NOT NULL,
    end_date TEXT,

    active INTEGER NOT NULL DEFAULT 1
        CHECK (active IN (0, 1)),

    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY(chore_id) REFERENCES chores(id),
    FOREIGN KEY(child_id) REFERENCES users(id),

    CHECK (
        day_of_month IS NULL
        OR day_of_month BETWEEN 1 AND 28
    ),

    CHECK (
        end_date IS NULL
        OR end_date >= start_date
    )
);

ALTER TABLE assignments
ADD COLUMN schedule_id INTEGER
REFERENCES quest_schedules(id);

CREATE UNIQUE INDEX IF NOT EXISTS assignments_unique_daily
ON assignments (
    chore_id,
    child_id,
    due_date
);

CREATE INDEX IF NOT EXISTS quest_schedules_active_index
ON quest_schedules (
    active,
    start_date,
    end_date
);

PRAGMA foreign_keys = ON;
