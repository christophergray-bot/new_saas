-- Family Quest Center Developer Notes
-- File: migrations/add_parent_security.sql
-- Purpose: Defines database schema or migration operations for add parent security.
-- Maintenance: Back up data and test migrations against a copy before production use.
-- Documentation updated: 2026-07-31

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
