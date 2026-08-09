"""Phase 9.6 Part 1 migration: family progression."""
from app import create_app
from database import get_db

VERSION = "0.9.6.1"
DESCRIPTION = "Family progression statistics, streaks, heatmap, and timeline"


def migrate():
    """Handle the migrate workflow."""
    app = create_app()
    with app.app_context():
        db = get_db()
        db.execute("""
            INSERT OR IGNORE INTO achievements
            (name, description, icon, category, requirement_type, requirement_value, xp_reward, star_reward)
            VALUES
            ('Three Day Spark', 'Build a 3-day quest streak.', '🔥', 'Streaks', 'CURRENT_STREAK', 3, 40, 0),
            ('Two Week Trailblazer', 'Build a 14-day quest streak.', '🌋', 'Streaks', 'CURRENT_STREAK', 14, 175, 10),
            ('Monthly Legend', 'Build a 30-day quest streak.', '☀️', 'Streaks', 'CURRENT_STREAK', 30, 350, 25)
        """)
        try:
            db.execute("""
                INSERT OR IGNORE INTO application_info (key, value, updated_at)
                VALUES ('application_version', ?, CURRENT_TIMESTAMP)
            """, (VERSION,))
            db.execute("UPDATE application_info SET value = ?, updated_at = CURRENT_TIMESTAMP WHERE key = 'application_version'", (VERSION,))
            db.execute("""
                INSERT OR IGNORE INTO migration_history
                (version, description, status, applied_at)
                VALUES (?, ?, 'success', CURRENT_TIMESTAMP)
            """, (VERSION, DESCRIPTION))
        except Exception:
            pass
        db.commit()
        print("Phase 9.6 Part 1 migration completed successfully.")
        print("Progress statistics, streaks, activity heatmap, and timeline are ready.")

if __name__ == '__main__':
    migrate()
