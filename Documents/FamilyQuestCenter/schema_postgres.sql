-- Generated PostgreSQL schema for Family Quest Center

BEGIN;

CREATE TABLE achievements (
    id BIGSERIAL PRIMARY KEY,
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
, is_system INTEGER NOT NULL DEFAULT 1, series_key TEXT, tier INTEGER NOT NULL DEFAULT 1);

CREATE TABLE application_info (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE assignments (
    id BIGSERIAL PRIMARY KEY,
    chore_id INTEGER NOT NULL,
    child_id INTEGER NOT NULL,
    due_date TEXT,
    status TEXT NOT NULL DEFAULT 'assigned',
    completed_at TEXT,
    approved_at TEXT, schedule_id INTEGER
REFERENCES quest_schedules(id), chain_instance_id INTEGER, chain_step_id INTEGER, family_id INTEGER,

    FOREIGN KEY(chore_id) REFERENCES chores(id),
    FOREIGN KEY(child_id) REFERENCES users(id)
);

CREATE TABLE audit_log (
    id BIGSERIAL PRIMARY KEY,
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
    id BIGSERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,
    difficulty INTEGER NOT NULL DEFAULT 1,
    stars INTEGER NOT NULL DEFAULT 10,
    approval_required INTEGER NOT NULL DEFAULT 1,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
, family_id INTEGER);

CREATE TABLE error_log (
    id BIGSERIAL PRIMARY KEY,
    error_type TEXT NOT NULL,
    message TEXT NOT NULL,
    traceback_text TEXT,
    request_path TEXT,
    resolved INTEGER NOT NULL DEFAULT 0 CHECK(resolved IN (0,1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE family_challenges(id BIGSERIAL PRIMARY KEY,name TEXT NOT NULL,description TEXT,goal_type TEXT NOT NULL,target_value INTEGER NOT NULL,start_date TEXT NOT NULL,end_date TEXT NOT NULL,reward_text TEXT,active INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, family_id INTEGER);

CREATE TABLE "legacy_rewards_phase_8" (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    type TEXT,
    value INTEGER DEFAULT 0,
    probability INTEGER DEFAULT 100,
    active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE migration_history (
    id BIGSERIAL PRIMARY KEY,
    version TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'success',
    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE notification_dismissals (
            notification_key TEXT PRIMARY KEY,
            dismissed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        , family_id INTEGER);

CREATE TABLE point_history (
    id BIGSERIAL PRIMARY KEY,
    child_id INTEGER NOT NULL,
    assignment_id INTEGER,
    points INTEGER NOT NULL,
    reason TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, family_id INTEGER,

    FOREIGN KEY(child_id) REFERENCES users(id),
    FOREIGN KEY(assignment_id) REFERENCES assignments(id)
);

CREATE TABLE quest_chain_instances(id BIGSERIAL PRIMARY KEY,chain_id INTEGER NOT NULL,child_id INTEGER NOT NULL,status TEXT NOT NULL DEFAULT 'active',started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,completed_at TEXT,due_date TEXT, family_id INTEGER,FOREIGN KEY(chain_id) REFERENCES quest_chains(id),FOREIGN KEY(child_id) REFERENCES users(id));

CREATE TABLE quest_chain_steps(id BIGSERIAL PRIMARY KEY,chain_id INTEGER NOT NULL,chore_id INTEGER NOT NULL,step_order INTEGER NOT NULL,FOREIGN KEY(chain_id) REFERENCES quest_chains(id),FOREIGN KEY(chore_id) REFERENCES chores(id),UNIQUE(chain_id,step_order));

CREATE TABLE quest_chains(id BIGSERIAL PRIMARY KEY,name TEXT NOT NULL,description TEXT,bonus_xp INTEGER NOT NULL DEFAULT 0,bonus_stars INTEGER NOT NULL DEFAULT 0,ordered_steps INTEGER NOT NULL DEFAULT 1,active INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, family_id INTEGER);

CREATE TABLE quest_schedules (
    id BIGSERIAL PRIMARY KEY,
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
                id BIGSERIAL PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                icon TEXT NOT NULL DEFAULT '🎁',
                display_order INTEGER NOT NULL DEFAULT 0,
                active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            , family_id INTEGER);

CREATE TABLE reward_history (
    id BIGSERIAL PRIMARY KEY,
    child_id INTEGER NOT NULL,
    reward_id INTEGER NOT NULL,
    earned_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    redeemed_at TEXT, family_id INTEGER,

    FOREIGN KEY(child_id) REFERENCES users(id),
    FOREIGN KEY(reward_id) REFERENCES "legacy_rewards_phase_8"(id)
);

CREATE TABLE reward_requests (
                id BIGSERIAL PRIMARY KEY,
                reward_id INTEGER NOT NULL,
                child_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending'
                    CHECK(status IN ('pending','approved','denied','redeemed')),
                requested_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                approved_at TEXT,
                denied_at TEXT,
                redeemed_at TEXT,
                approved_by INTEGER,
                notes TEXT, family_id INTEGER,
                FOREIGN KEY(reward_id) REFERENCES rewards(id),
                FOREIGN KEY(child_id) REFERENCES users(id),
                FOREIGN KEY(approved_by) REFERENCES users(id)
            );

CREATE TABLE rewards (
                id BIGSERIAL PRIMARY KEY,
                category_id INTEGER,
                name TEXT NOT NULL,
                description TEXT,
                icon TEXT NOT NULL DEFAULT '🎁',
                cost INTEGER NOT NULL CHECK(cost > 0),
                quantity INTEGER CHECK(quantity IS NULL OR quantity >= 0),
                requires_approval INTEGER NOT NULL DEFAULT 1 CHECK(requires_approval IN (0,1)),
                active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, image_filename TEXT, family_id INTEGER,
                FOREIGN KEY(category_id) REFERENCES reward_categories(id)
            );

CREATE TABLE settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE star_transactions (
                id BIGSERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                amount INTEGER NOT NULL CHECK(amount != 0),
                transaction_type TEXT NOT NULL,
                reference_type TEXT,
                reference_id INTEGER,
                description TEXT NOT NULL,
                idempotency_key TEXT UNIQUE,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, family_id INTEGER,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );

CREATE TABLE user_achievements (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    achievement_id INTEGER NOT NULL,
    earned_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    notified_at TEXT, family_id INTEGER,

    FOREIGN KEY(user_id) REFERENCES users(id),
    FOREIGN KEY(achievement_id) REFERENCES achievements(id),

    UNIQUE(user_id, achievement_id)
);

CREATE TABLE users (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('parent', 'child')),
    initial TEXT NOT NULL,
    total_points INTEGER NOT NULL DEFAULT 0,
    current_level INTEGER NOT NULL DEFAULT 1,
    current_streak INTEGER NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
, total_xp INTEGER NOT NULL DEFAULT 0, avatar_key TEXT NOT NULL DEFAULT 'adventurer', title_key TEXT NOT NULL DEFAULT 'adventurer', frame_key TEXT NOT NULL DEFAULT 'bronze', theme_key TEXT NOT NULL DEFAULT 'quest', family_id INTEGER);

CREATE TABLE xp_history (
    id BIGSERIAL PRIMARY KEY,
    child_id INTEGER NOT NULL,
    assignment_id INTEGER,
    xp INTEGER NOT NULL,
    reason TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, family_id INTEGER,

    FOREIGN KEY(child_id) REFERENCES users(id),
    FOREIGN KEY(assignment_id) REFERENCES assignments(id)
);

CREATE TABLE families (
                id BIGSERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                slug TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active', 'suspended', 'archived')),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

CREATE TABLE account_users (
                id BIGSERIAL PRIMARY KEY,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                display_name TEXT NOT NULL,
                email_verified INTEGER NOT NULL DEFAULT 0
                    CHECK (email_verified IN (0, 1)),
                active INTEGER NOT NULL DEFAULT 1
                    CHECK (active IN (0, 1)),
                last_login_at TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

CREATE TABLE family_memberships (
                id BIGSERIAL PRIMARY KEY,
                family_id INTEGER NOT NULL,
                account_user_id INTEGER NOT NULL,
                role TEXT NOT NULL DEFAULT 'parent'
                    CHECK (role IN ('owner', 'parent', 'caregiver')),
                active INTEGER NOT NULL DEFAULT 1
                    CHECK (active IN (0, 1)),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (family_id) REFERENCES families(id),
                FOREIGN KEY (account_user_id) REFERENCES account_users(id),
                UNIQUE (family_id, account_user_id)
            );

CREATE TABLE family_onboarding (
                family_id INTEGER PRIMARY KEY,
                approvals_acknowledged INTEGER NOT NULL DEFAULT 0,
                setup_completed INTEGER NOT NULL DEFAULT 0,
                completed_at TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (family_id) REFERENCES families(id)
            );

CREATE TABLE child_training (
                child_id INTEGER PRIMARY KEY,
                training_completed INTEGER NOT NULL DEFAULT 0,
                completed_at TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (child_id) REFERENCES users(id)
            );

CREATE TABLE security_rate_limits (
            action TEXT NOT NULL,
            subject_hash TEXT NOT NULL,
            window_started_at TEXT NOT NULL,
            attempt_count INTEGER NOT NULL DEFAULT 0,
            blocked_until TEXT,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(action, subject_hash)
        );

CREATE TABLE content_packs (
            pack_key TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            version TEXT NOT NULL,
            category TEXT NOT NULL,
            description TEXT,
            icon TEXT NOT NULL DEFAULT '📦',
            pack_type TEXT NOT NULL DEFAULT 'expansion',
            author TEXT NOT NULL DEFAULT 'Family Quest Center',
            archive_allowed INTEGER NOT NULL DEFAULT 1,
            price_type TEXT NOT NULL DEFAULT 'free',
            price_cents INTEGER NOT NULL DEFAULT 0,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

CREATE TABLE family_content_packs (
            id BIGSERIAL PRIMARY KEY,
            family_id INTEGER NOT NULL,
            pack_key TEXT NOT NULL,
            installed_version TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','archived')),
            installed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(family_id, pack_key),
            FOREIGN KEY(family_id) REFERENCES families(id),
            FOREIGN KEY(pack_key) REFERENCES content_packs(pack_key)
        );

CREATE TABLE content_pack_requests (
            id BIGSERIAL PRIMARY KEY,
            family_id INTEGER NOT NULL,
            pack_key TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','denied')),
            requested_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            resolved_at TEXT,
            UNIQUE(family_id, pack_key),
            FOREIGN KEY(family_id) REFERENCES families(id),
            FOREIGN KEY(pack_key) REFERENCES content_packs(pack_key)
        );

CREATE TABLE content_pack_items (
            id BIGSERIAL PRIMARY KEY,
            family_id INTEGER NOT NULL,
            pack_key TEXT NOT NULL,
            item_type TEXT NOT NULL,
            item_id INTEGER NOT NULL,
            item_archived INTEGER NOT NULL DEFAULT 0,
            pack_archived INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(family_id, pack_key, item_type, item_id)
        );

CREATE TABLE journeys (
        id BIGSERIAL PRIMARY KEY,
        name TEXT NOT NULL,
        description TEXT,
        xp_reward INTEGER NOT NULL DEFAULT 25 CHECK(xp_reward >= 0),
        difficulty INTEGER NOT NULL DEFAULT 1 CHECK(difficulty BETWEEN 1 AND 5),
        estimated_minutes INTEGER,
        active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        family_id INTEGER
    );

CREATE TABLE adventures_v2 (
        id BIGSERIAL PRIMARY KEY,
        name TEXT NOT NULL,
        description TEXT,
        bonus_xp INTEGER NOT NULL DEFAULT 100 CHECK(bonus_xp >= 0),
        active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        family_id INTEGER
    );

CREATE TABLE adventure_journeys (
        id BIGSERIAL PRIMARY KEY,
        adventure_id INTEGER NOT NULL,
        journey_id INTEGER NOT NULL,
        step_order INTEGER NOT NULL,
        FOREIGN KEY(adventure_id) REFERENCES adventures_v2(id),
        FOREIGN KEY(journey_id) REFERENCES journeys(id),
        UNIQUE(adventure_id, step_order)
    );

CREATE TABLE adventure_instances_v2 (
        id BIGSERIAL PRIMARY KEY,
        adventure_id INTEGER NOT NULL,
        child_id INTEGER NOT NULL,
        start_date TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','completed','cancelled')),
        completed_at TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        family_id INTEGER, pending_approval INTEGER NOT NULL DEFAULT 0, submitted_at TEXT, parent_message TEXT,
        FOREIGN KEY(adventure_id) REFERENCES adventures_v2(id),
        FOREIGN KEY(child_id) REFERENCES users(id)
    );

CREATE TABLE journey_instances (
        id BIGSERIAL PRIMARY KEY,
        adventure_instance_id INTEGER NOT NULL,
        journey_id INTEGER NOT NULL,
        step_order INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'locked' CHECK(status IN ('locked','assigned','completed')),
        pending_approval INTEGER NOT NULL DEFAULT 0 CHECK(pending_approval IN (0,1)),
        submitted_at TEXT,
        completed_at TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, family_id INTEGER,
        FOREIGN KEY(adventure_instance_id) REFERENCES adventure_instances_v2(id),
        FOREIGN KEY(journey_id) REFERENCES journeys(id),
        UNIQUE(adventure_instance_id, step_order)
    );

CREATE TABLE family_achievements (
            id BIGSERIAL PRIMARY KEY,
            family_id INTEGER NOT NULL,
            achievement_id INTEGER NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(family_id, achievement_id),
            FOREIGN KEY(achievement_id) REFERENCES achievements(id)
        );

CREATE TABLE family_cosmetics (
            id BIGSERIAL PRIMARY KEY,
            family_id INTEGER NOT NULL,
            category TEXT NOT NULL CHECK(category IN ('avatars','frames','themes')),
            item_key TEXT NOT NULL,
            name TEXT NOT NULL,
            icon TEXT NOT NULL,
            class_name TEXT,
            unlock_type TEXT NOT NULL DEFAULT 'ALWAYS',
            unlock_value INTEGER NOT NULL DEFAULT 0,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(family_id, category, item_key)
        );

CREATE TABLE family_security (
            family_id INTEGER PRIMARY KEY,
            parent_pin_hash TEXT,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (family_id) REFERENCES families(id)
        );

CREATE TABLE parent_invitations (
            id BIGSERIAL PRIMARY KEY,
            family_id INTEGER NOT NULL,
            email TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'parent' CHECK(role='parent'),
            token TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','accepted','cancelled')),
            invited_by_account_id INTEGER,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            accepted_at TEXT,
            UNIQUE(family_id, email, status),
            FOREIGN KEY(family_id) REFERENCES families(id),
            FOREIGN KEY(invited_by_account_id) REFERENCES account_users(id)
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

CREATE INDEX idx_family_memberships_family
                ON family_memberships(family_id);

CREATE INDEX idx_family_memberships_account
                ON family_memberships(account_user_id);

CREATE INDEX "idx_users_family_id" ON "users" (family_id);

CREATE INDEX "idx_chores_family_id" ON "chores" (family_id);

CREATE INDEX "idx_assignments_family_id" ON "assignments" (family_id);

CREATE INDEX "idx_quest_schedules_family_id" ON "quest_schedules" (family_id);

CREATE INDEX "idx_quest_chains_family_id" ON "quest_chains" (family_id);

CREATE INDEX "idx_quest_chain_instances_family_id" ON "quest_chain_instances" (family_id);

CREATE INDEX "idx_family_challenges_family_id" ON "family_challenges" (family_id);

CREATE INDEX "idx_rewards_family_id" ON "rewards" (family_id);

CREATE INDEX "idx_reward_categories_family_id" ON "reward_categories" (family_id);

CREATE INDEX "idx_reward_requests_family_id" ON "reward_requests" (family_id);

CREATE INDEX "idx_reward_history_family_id" ON "reward_history" (family_id);

CREATE INDEX "idx_star_transactions_family_id" ON "star_transactions" (family_id);

CREATE INDEX "idx_point_history_family_id" ON "point_history" (family_id);

CREATE INDEX "idx_xp_history_family_id" ON "xp_history" (family_id);

CREATE INDEX "idx_user_achievements_family_id" ON "user_achievements" (family_id);

CREATE INDEX "idx_notification_dismissals_family_id" ON "notification_dismissals" (family_id);

CREATE INDEX idx_achievements_series ON achievements(series_key,tier,active);

CREATE INDEX idx_family_content_packs_family ON family_content_packs(family_id,status);
CREATE INDEX idx_content_pack_requests_family ON content_pack_requests(family_id,status);

CREATE INDEX idx_content_pack_items_family ON content_pack_items(family_id,pack_key,item_type);

CREATE INDEX idx_journeys_family_id ON journeys(family_id);

CREATE INDEX idx_adventures_v2_family_id ON adventures_v2(family_id);

CREATE INDEX idx_adventure_instances_v2_family_id ON adventure_instances_v2(family_id);

CREATE INDEX idx_family_achievements_family
            ON family_achievements(family_id, active);

CREATE INDEX idx_family_cosmetics_family
            ON family_cosmetics(family_id, category, active);

CREATE INDEX "idx_journey_instances_family_id" ON "journey_instances" (family_id);

COMMIT;
