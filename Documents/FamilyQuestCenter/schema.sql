-- Family Quest Center Developer Notes
-- File: schema.sql
-- Purpose: Defines database schema or migration operations for schema.
-- Maintenance: Back up data and test migrations against a copy before production use.
-- Documentation updated: 2026-07-31

BEGIN TRANSACTION;
CREATE TABLE achievements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL,
    icon TEXT NOT NULL DEFAULT '🏆',
    category TEXT NOT NULL,
    requirement_type TEXT NOT NULL,
    requirement_value INTEGER NOT NULL CHECK (requirement_value >= 0),
    xp_reward INTEGER NOT NULL DEFAULT 0 CHECK (xp_reward >= 0),
    star_reward INTEGER NOT NULL DEFAULT 0 CHECK (star_reward >= 0),
    hidden INTEGER NOT NULL DEFAULT 0 CHECK (hidden IN (0, 1)),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
INSERT INTO "achievements" VALUES(1,'First Steps','Complete your first approved mission.','👣','Core Milestones','QUESTS_COMPLETED',1,25,5,0,1,'2026-07-31 00:00:00');
INSERT INTO "achievements" VALUES(2,'First Spark','Earn 100 lifetime stars.','⭐','Core Milestones','STARS_EARNED',100,40,0,0,1,'2026-07-31 00:00:00');
INSERT INTO "achievements" VALUES(3,'Early Riser','Build a 3-day mission streak.','🌅','Core Milestones','CURRENT_STREAK',3,40,5,0,1,'2026-07-31 00:00:00');
INSERT INTO "achievements" VALUES(4,'Trail Learner','Earn 100 lifetime XP.','🗺️','Core Milestones','TOTAL_XP',100,0,10,0,1,'2026-07-31 00:00:00');
INSERT INTO "achievements" VALUES(5,'Forest Scout','Reach explorer level 5.','🦌','Core Milestones','LEVEL',5,100,15,0,1,'2026-07-31 00:00:00');
INSERT INTO "achievements" VALUES(6,'Wilderness Ranger','Reach explorer level 10.','🌲','Core Milestones','LEVEL',10,200,30,0,1,'2026-07-31 00:00:00');
CREATE TABLE application_info (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
INSERT INTO "application_info" VALUES('application_name','Family Quest Center','2026-07-29 01:20:19');
INSERT INTO "application_info" VALUES('application_version','1.0.0','2026-07-29 01:20:19');
INSERT INTO "application_info" VALUES('database_version','1.0.0','2026-07-29 01:20:19');
INSERT INTO "application_info" VALUES('version','1.0.0','2026-07-29 01:20:19');
CREATE TABLE assignments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chore_id INTEGER NOT NULL,
    child_id INTEGER NOT NULL,
    due_date TEXT,
    status TEXT NOT NULL DEFAULT 'assigned',
    completed_at TEXT,
    approved_at TEXT, schedule_id INTEGER
REFERENCES quest_schedules(id), chain_instance_id INTEGER, chain_step_id INTEGER,

    FOREIGN KEY(chore_id) REFERENCES chores(id),
    FOREIGN KEY(child_id) REFERENCES users(id)
);
CREATE TABLE audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    family_id INTEGER,
    actor_type TEXT NOT NULL DEFAULT 'system',
    actor_name TEXT,
    action TEXT NOT NULL,
    entity_type TEXT,
    entity_id INTEGER,
    details TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE chores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT,
    difficulty INTEGER NOT NULL DEFAULT 1,
    stars INTEGER NOT NULL DEFAULT 10,
    approval_required INTEGER NOT NULL DEFAULT 1,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE error_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    error_type TEXT NOT NULL,
    message TEXT NOT NULL,
    traceback_text TEXT,
    request_path TEXT,
    resolved INTEGER NOT NULL DEFAULT 0 CHECK(resolved IN (0,1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE family_challenges(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,description TEXT,goal_type TEXT NOT NULL,target_value INTEGER NOT NULL,start_date TEXT NOT NULL,end_date TEXT NOT NULL,reward_text TEXT,active INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE "legacy_rewards_phase_8" (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT,
    type TEXT,
    value INTEGER DEFAULT 0,
    probability INTEGER DEFAULT 100,
    active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE migration_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    version TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'success',
    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
INSERT INTO "migration_history" VALUES(1,'7.0','Parent PIN security','success','2026-07-26 20:53:16');
INSERT INTO "migration_history" VALUES(2,'8.1','Character progression and XP','success','2026-07-26 20:53:16');
INSERT INTO "migration_history" VALUES(3,'8.2','Achievement system','success','2026-07-26 20:53:16');
INSERT INTO "migration_history" VALUES(4,'8.3','Character customization','success','2026-07-26 20:53:16');
INSERT INTO "migration_history" VALUES(5,'9.1','Reward economy and star ledger','success','2026-07-26 20:53:16');
INSERT INTO "migration_history" VALUES(6,'9.2','Reward shop and request workflow','success','2026-07-26 20:53:16');
INSERT INTO "migration_history" VALUES(7,'9.5.1','Responsive application shell and UI components','success','2026-07-26 20:53:16');
INSERT INTO "migration_history" VALUES(8,'9.5.2','Administration, diagnostics, audit, and error logging','success','2026-07-26 20:53:16');
INSERT INTO "migration_history" VALUES(9,'0.9.6.1','Family progression statistics, streaks, heatmap, and timeline','success','2026-07-26 21:04:44');
INSERT INTO "migration_history" VALUES(10,'0.9.6.2','Quest chains and family challenges','success','2026-07-26 21:16:51');
INSERT INTO "migration_history" VALUES(11,'0.9.8.0','Added editable family, quest-default, daily-rule, and session settings.','success','2026-07-26 22:07:28');
INSERT INTO "migration_history" VALUES(12,'1.0.0-RC1','Clean Version 1.0 release-candidate database','success','2026-07-26 22:21:03');
CREATE TABLE notification_dismissals (
            notification_key TEXT PRIMARY KEY,
            dismissed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
CREATE TABLE point_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    child_id INTEGER NOT NULL,
    assignment_id INTEGER,
    points INTEGER NOT NULL,
    reason TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY(child_id) REFERENCES users(id),
    FOREIGN KEY(assignment_id) REFERENCES assignments(id)
);
CREATE TABLE quest_chain_instances(id INTEGER PRIMARY KEY AUTOINCREMENT,chain_id INTEGER NOT NULL,child_id INTEGER NOT NULL,status TEXT NOT NULL DEFAULT 'active',started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,completed_at TEXT,due_date TEXT,FOREIGN KEY(chain_id) REFERENCES quest_chains(id),FOREIGN KEY(child_id) REFERENCES users(id));
CREATE TABLE quest_chain_steps(id INTEGER PRIMARY KEY AUTOINCREMENT,chain_id INTEGER NOT NULL,chore_id INTEGER NOT NULL,step_order INTEGER NOT NULL,FOREIGN KEY(chain_id) REFERENCES quest_chains(id),FOREIGN KEY(chore_id) REFERENCES chores(id),UNIQUE(chain_id,step_order));
CREATE TABLE quest_chains(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,description TEXT,bonus_xp INTEGER NOT NULL DEFAULT 0,bonus_stars INTEGER NOT NULL DEFAULT 0,ordered_steps INTEGER NOT NULL DEFAULT 1,active INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE quest_schedules (
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
    assignment_status TEXT NOT NULL DEFAULT 'active'
        CHECK (assignment_status IN ('active', 'paused', 'unassigned')),
    unassigned_at TEXT,

    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    family_id INTEGER,

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
CREATE TABLE reward_categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                icon TEXT NOT NULL DEFAULT '🎁',
                display_order INTEGER NOT NULL DEFAULT 0,
                active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
INSERT INTO "reward_categories" VALUES(1,'Food','🍦',10,1,'2026-07-26 15:13:55');
INSERT INTO "reward_categories" VALUES(2,'Screen Time','🎮',20,1,'2026-07-26 15:13:55');
INSERT INTO "reward_categories" VALUES(3,'Activities','🎬',30,1,'2026-07-26 15:13:55');
INSERT INTO "reward_categories" VALUES(4,'Privileges','👑',40,1,'2026-07-26 15:13:55');
INSERT INTO "reward_categories" VALUES(5,'Family','👨‍👩‍👧',50,1,'2026-07-26 15:13:55');
CREATE TABLE reward_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    child_id INTEGER NOT NULL,
    reward_id INTEGER NOT NULL,
    earned_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    redeemed_at TEXT,

    FOREIGN KEY(child_id) REFERENCES users(id),
    FOREIGN KEY(reward_id) REFERENCES "legacy_rewards_phase_8"(id)
);
CREATE TABLE reward_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reward_id INTEGER NOT NULL,
                child_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending'
                    CHECK(status IN ('pending','approved','denied','redeemed')),
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
CREATE TABLE rewards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category_id INTEGER,
                name TEXT NOT NULL,
                description TEXT,
                icon TEXT NOT NULL DEFAULT '🎁',
                cost INTEGER NOT NULL CHECK(cost > 0),
                quantity INTEGER CHECK(quantity IS NULL OR quantity >= 0),
                requires_approval INTEGER NOT NULL DEFAULT 1 CHECK(requires_approval IN (0,1)),
                active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, image_filename TEXT,
                FOREIGN KEY(category_id) REFERENCES reward_categories(id)
            );
CREATE TABLE settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE family_settings (
    family_id INTEGER NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (family_id, key),
    FOREIGN KEY (family_id) REFERENCES families(id) ON DELETE CASCADE
);
CREATE INDEX idx_family_settings_family ON family_settings(family_id);
INSERT INTO "settings" VALUES('application_name','Family Quest Center');
INSERT INTO "settings" VALUES('family_name','Our Family');
INSERT INTO "settings" VALUES('default_quest_difficulty','1');
INSERT INTO "settings" VALUES('default_quest_stars','1');
INSERT INTO "settings" VALUES('default_approval_required','1');
INSERT INTO "settings" VALUES('daily_reset_time','04:00');
INSERT INTO "settings" VALUES('streak_grace_days','3');
INSERT INTO "settings" VALUES('session_timeout_minutes','600');
CREATE TABLE star_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                amount INTEGER NOT NULL CHECK(amount != 0),
                transaction_type TEXT NOT NULL,
                reference_type TEXT,
                reference_id INTEGER,
                description TEXT NOT NULL,
                idempotency_key TEXT UNIQUE,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );
CREATE TABLE user_achievements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    achievement_id INTEGER NOT NULL,
    earned_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    notified_at TEXT,

    FOREIGN KEY(user_id) REFERENCES users(id),
    FOREIGN KEY(achievement_id) REFERENCES achievements(id),

    UNIQUE(user_id, achievement_id)
);
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('parent', 'child')),
    initial TEXT NOT NULL,
    total_points INTEGER NOT NULL DEFAULT 0,
    current_level INTEGER NOT NULL DEFAULT 1,
    current_streak INTEGER NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
, total_xp INTEGER NOT NULL DEFAULT 0, avatar_key TEXT NOT NULL DEFAULT 'adventurer', title_key TEXT NOT NULL DEFAULT 'adventurer', frame_key TEXT NOT NULL DEFAULT 'bronze', theme_key TEXT NOT NULL DEFAULT 'quest');
CREATE TABLE xp_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    child_id INTEGER NOT NULL,
    assignment_id INTEGER,
    xp INTEGER NOT NULL,
    reason TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY(child_id) REFERENCES users(id),
    FOREIGN KEY(assignment_id) REFERENCES assignments(id)
);
CREATE UNIQUE INDEX assignments_unique_daily
ON assignments (
    chore_id,
    child_id,
    due_date
)
WHERE chain_instance_id IS NULL;
CREATE INDEX quest_schedules_active_index
ON quest_schedules (
    active,
    start_date,
    end_date
);
CREATE INDEX idx_quest_schedules_family_active
ON quest_schedules (family_id, active, start_date, end_date);
CREATE UNIQUE INDEX xp_history_assignment_unique
ON xp_history (assignment_id)
WHERE assignment_id IS NOT NULL;
CREATE INDEX user_achievements_user_index
ON user_achievements (user_id, earned_at);
CREATE INDEX star_transactions_user_date
            ON star_transactions(user_id, created_at DESC);
CREATE INDEX reward_requests_child_date
            ON reward_requests(child_id, requested_at DESC);
CREATE INDEX reward_requests_status_date
            ON reward_requests(status, requested_at DESC);
CREATE UNIQUE INDEX reward_requests_one_pending
            ON reward_requests(child_id, reward_id)
            WHERE status='pending';
CREATE INDEX audit_log_created_index ON audit_log(created_at DESC);
CREATE INDEX audit_log_action_index ON audit_log(action);
CREATE INDEX audit_log_family_index ON audit_log(family_id, created_at DESC);
CREATE INDEX error_log_created_index ON error_log(created_at DESC);
DELETE FROM "sqlite_sequence";
INSERT INTO "sqlite_sequence" VALUES('achievements',25);
INSERT INTO "sqlite_sequence" VALUES('reward_categories',7);
INSERT INTO "sqlite_sequence" VALUES('migration_history',12);
COMMIT;
