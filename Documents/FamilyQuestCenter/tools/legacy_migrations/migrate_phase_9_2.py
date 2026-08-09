"""Safe Phase 9.2 migration for Family Quest Center."""
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
        reward_columns = columns(conn, "rewards")
        if not reward_columns:
            raise RuntimeError("The rewards table is missing. Run migrate_phase_9_1.py first.")
        if "image_filename" not in reward_columns:
            conn.execute("ALTER TABLE rewards ADD COLUMN image_filename TEXT")
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS reward_requests (
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
            CREATE INDEX IF NOT EXISTS reward_requests_child_date
            ON reward_requests(child_id, requested_at DESC);
            CREATE INDEX IF NOT EXISTS reward_requests_status_date
            ON reward_requests(status, requested_at DESC);
            CREATE UNIQUE INDEX IF NOT EXISTS reward_requests_one_pending
            ON reward_requests(child_id, reward_id)
            WHERE status='pending';
        """)
        conn.commit()
        print("Phase 9.2 Reward Shop migration completed successfully.")
        print("Reward requests and optional reward images are ready.")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
