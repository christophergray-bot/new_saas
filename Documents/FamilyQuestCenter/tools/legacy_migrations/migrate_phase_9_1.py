"""Safe Phase 9.1 migration for Family Quest Center."""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).with_name("chorce.db")

def columns(conn, table):
    """Handle the columns workflow."""
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}

def main():
    """Handle the main workflow."""
    if not DB_PATH.exists():
        raise SystemExit(f"Database not found: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.execute("BEGIN")
        # Preserve the old prototype rewards table rather than deleting data.
        old_cols = columns(conn, "rewards")
        if old_cols and "cost" not in old_cols:
            legacy_name = "legacy_rewards_phase_8"
            if not columns(conn, legacy_name):
                conn.execute(f"ALTER TABLE rewards RENAME TO {legacy_name}")
            else:
                conn.execute("DROP TABLE rewards")

        conn.executescript("""
            CREATE TABLE IF NOT EXISTS reward_categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                icon TEXT NOT NULL DEFAULT '🎁',
                display_order INTEGER NOT NULL DEFAULT 0,
                active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS rewards (
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
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(category_id) REFERENCES reward_categories(id)
            );
            CREATE TABLE IF NOT EXISTS star_transactions (
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
            CREATE INDEX IF NOT EXISTS star_transactions_user_date
            ON star_transactions(user_id, created_at DESC);
        """)
        conn.executemany(
            "INSERT OR IGNORE INTO reward_categories(name,icon,display_order) VALUES(?,?,?)",
            [('Food','🍦',10),('Screen Time','🎮',20),('Activities','🎬',30),('Privileges','👑',40),('Family','👨‍👩‍👧',50)],
        )
        # Backfill each existing balance once so no stars are lost.
        users = conn.execute("SELECT id, total_points FROM users WHERE role='child'").fetchall()
        for user_id, balance in users:
            exists = conn.execute("SELECT 1 FROM star_transactions WHERE user_id=? LIMIT 1", (user_id,)).fetchone()
            if not exists and int(balance or 0) != 0:
                conn.execute("""INSERT INTO star_transactions(user_id,amount,transaction_type,description,idempotency_key)
                              VALUES(?,?,'MIGRATION','Opening balance from Phase 8',?)""",
                             (user_id, int(balance), f"phase9-opening:{user_id}"))
        conn.commit()
        print("Phase 9.1 reward economy migration completed successfully.")
        print("Existing star balances were preserved as opening ledger entries.")
    except Exception:
        conn.rollback(); raise
    finally:
        conn.close()

if __name__ == '__main__': main()
