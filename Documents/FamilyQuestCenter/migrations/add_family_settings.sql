-- FC-0019: isolate parent-managed settings by family.
CREATE TABLE IF NOT EXISTS family_settings (
    family_id INTEGER NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (family_id, key),
    FOREIGN KEY (family_id) REFERENCES families(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_family_settings_family
    ON family_settings(family_id);
