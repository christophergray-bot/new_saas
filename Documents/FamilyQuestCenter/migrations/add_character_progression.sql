-- Family Quest Center Developer Notes
-- File: migrations/add_character_progression.sql
-- Purpose: Defines database schema or migration operations for add character progression.
-- Maintenance: Back up data and test migrations against a copy before production use.
-- Documentation updated: 2026-07-31

-- Phase 8 migration for an EXISTING Family Quest Center database.
-- Run this once. Do not run schema.sql against an existing database.

ALTER TABLE users
ADD COLUMN total_xp INTEGER NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS xp_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    child_id INTEGER NOT NULL,
    assignment_id INTEGER,
    xp INTEGER NOT NULL,
    reason TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY(child_id) REFERENCES users(id),
    FOREIGN KEY(assignment_id) REFERENCES assignments(id)
);

CREATE UNIQUE INDEX IF NOT EXISTS xp_history_assignment_unique
ON xp_history (assignment_id)
WHERE assignment_id IS NOT NULL;
