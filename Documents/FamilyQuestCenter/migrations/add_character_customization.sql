-- Family Quest Center Developer Notes
-- File: migrations/add_character_customization.sql
-- Purpose: Defines database schema or migration operations for add character customization.
-- Maintenance: Back up data and test migrations against a copy before production use.
-- Documentation updated: 2026-07-31

ALTER TABLE users ADD COLUMN avatar_key TEXT NOT NULL DEFAULT 'adventurer';
ALTER TABLE users ADD COLUMN title_key TEXT NOT NULL DEFAULT 'adventurer';
ALTER TABLE users ADD COLUMN frame_key TEXT NOT NULL DEFAULT 'bronze';
ALTER TABLE users ADD COLUMN theme_key TEXT NOT NULL DEFAULT 'quest';
