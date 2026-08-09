-- Family Quest Center Developer Notes
-- File: migrations/add_reward_shop.sql
-- Purpose: Defines database schema or migration operations for add reward shop.
-- Maintenance: Back up data and test migrations against a copy before production use.
-- Documentation updated: 2026-07-31

-- Phase 9.2 reference only. Use migrate_phase_9_2.py for an existing database.
ALTER TABLE rewards ADD COLUMN image_filename TEXT;
CREATE TABLE reward_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    reward_id INTEGER NOT NULL,
    child_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','denied','redeemed')),
    requested_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    approved_at TEXT,
    denied_at TEXT,
    redeemed_at TEXT,
    approved_by INTEGER,
    notes TEXT,
    FOREIGN KEY(reward_id) REFERENCES rewards(id),
    FOREIGN KEY(child_id) REFERENCES users(id),
    FOREIGN KEY(approved_by) REFERENCES users(id)
);
