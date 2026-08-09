-- Family Quest Center Developer Notes
-- File: migrations/add_quest_chains_family_challenges.sql
-- Purpose: Defines database schema or migration operations for add quest chains family challenges.
-- Maintenance: Back up data and test migrations against a copy before production use.
-- Documentation updated: 2026-07-31

PRAGMA foreign_keys=OFF;
CREATE TABLE IF NOT EXISTS quest_chains(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,description TEXT,bonus_xp INTEGER NOT NULL DEFAULT 0,bonus_stars INTEGER NOT NULL DEFAULT 0,ordered_steps INTEGER NOT NULL DEFAULT 1,active INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS quest_chain_steps(id INTEGER PRIMARY KEY AUTOINCREMENT,chain_id INTEGER NOT NULL,chore_id INTEGER NOT NULL,step_order INTEGER NOT NULL,FOREIGN KEY(chain_id) REFERENCES quest_chains(id),FOREIGN KEY(chore_id) REFERENCES chores(id),UNIQUE(chain_id,step_order));
CREATE TABLE IF NOT EXISTS quest_chain_instances(id INTEGER PRIMARY KEY AUTOINCREMENT,chain_id INTEGER NOT NULL,child_id INTEGER NOT NULL,status TEXT NOT NULL DEFAULT 'active',started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,completed_at TEXT,due_date TEXT,FOREIGN KEY(chain_id) REFERENCES quest_chains(id),FOREIGN KEY(child_id) REFERENCES users(id));
CREATE TABLE IF NOT EXISTS family_challenges(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,description TEXT,goal_type TEXT NOT NULL,target_value INTEGER NOT NULL,start_date TEXT NOT NULL,end_date TEXT NOT NULL,reward_text TEXT,active INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
