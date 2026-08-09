-- Achievement Engine v2 schema upgrade
ALTER TABLE achievements ADD COLUMN series_key TEXT;
ALTER TABLE achievements ADD COLUMN tier INTEGER NOT NULL DEFAULT 1;
CREATE INDEX IF NOT EXISTS idx_achievements_series ON achievements(series_key,tier,active);
