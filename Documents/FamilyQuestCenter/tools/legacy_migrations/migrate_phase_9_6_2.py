"""Family Quest Center developer documentation.

File: tools/legacy_migrations/migrate_phase_9_6_2.py
Purpose: Supports the migrate phase 9 6 2 portion of Family Quest Center.

Maintenance notes:
- Preserve tenant and family data isolation when changing queries.
- Keep route, template, and schema changes synchronized.
- Run regression tests before release packaging.
Documentation updated: 2026-07-31.
"""

from pathlib import Path
import sqlite3
DB=Path(__file__).with_name('chorce.db'); SQL=Path(__file__).with_name('migrations')/'add_quest_chains_family_challenges.sql'
with sqlite3.connect(DB) as db:
    db.executescript(SQL.read_text(encoding='utf-8'))
    cols={r[1] for r in db.execute('PRAGMA table_info(assignments)')}
    if 'chain_instance_id' not in cols: db.execute('ALTER TABLE assignments ADD COLUMN chain_instance_id INTEGER')
    if 'chain_step_id' not in cols: db.execute('ALTER TABLE assignments ADD COLUMN chain_step_id INTEGER')
    db.execute("INSERT OR REPLACE INTO application_info(key,value,updated_at) VALUES('application_version','0.9.6.2',CURRENT_TIMESTAMP)")
    db.execute("INSERT OR REPLACE INTO application_info(key,value,updated_at) VALUES('database_version','0.9.6.2',CURRENT_TIMESTAMP)")
    exists=db.execute("SELECT 1 FROM migration_history WHERE version='0.9.6.2'").fetchone()
    if not exists: db.execute("INSERT INTO migration_history(version,description,status) VALUES('0.9.6.2','Quest chains and family challenges','success')")
    db.commit()
print('Phase 9.6 Part 2 migration completed successfully.')
print('Quest chains and family challenges are ready.')
