-- Family Quest Center Developer Notes
-- File: migrations/add_administration_diagnostics.sql
-- Purpose: Defines database schema or migration operations for add administration diagnostics.
-- Maintenance: Back up data and test migrations against a copy before production use.
-- Documentation updated: 2026-07-31

CREATE TABLE IF NOT EXISTS application_info (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS migration_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    version TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'success',
    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_type TEXT NOT NULL DEFAULT 'system',
    actor_name TEXT,
    action TEXT NOT NULL,
    entity_type TEXT,
    entity_id INTEGER,
    details TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS audit_log_created_index ON audit_log(created_at DESC);
CREATE INDEX IF NOT EXISTS audit_log_action_index ON audit_log(action);

CREATE TABLE IF NOT EXISTS error_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    error_type TEXT NOT NULL,
    message TEXT NOT NULL,
    traceback_text TEXT,
    request_path TEXT,
    resolved INTEGER NOT NULL DEFAULT 0 CHECK(resolved IN (0,1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS error_log_created_index ON error_log(created_at DESC);

INSERT OR REPLACE INTO application_info(key, value, updated_at)
VALUES ('application_version', '0.9.5', CURRENT_TIMESTAMP),
       ('database_version', '9.5.2', CURRENT_TIMESTAMP),
       ('application_name', 'Family Quest Center', CURRENT_TIMESTAMP);

INSERT OR IGNORE INTO migration_history(version, description)
VALUES
('7.0', 'Parent PIN security'),
('8.1', 'Character progression and XP'),
('8.2', 'Achievement system'),
('8.3', 'Character customization'),
('9.1', 'Reward economy and star ledger'),
('9.2', 'Reward shop and request workflow'),
('9.5.1', 'Responsive application shell and UI components'),
('9.5.2', 'Administration, diagnostics, audit, and error logging');
