-- Family Quest Center RC1.8.4 Assignment Management
-- Existing installations are also upgraded automatically by the application.
ALTER TABLE quest_schedules ADD COLUMN assignment_status TEXT NOT NULL DEFAULT 'active';
ALTER TABLE quest_schedules ADD COLUMN unassigned_at TEXT;
UPDATE quest_schedules SET assignment_status=CASE WHEN active=1 THEN 'active' ELSE 'paused' END;
