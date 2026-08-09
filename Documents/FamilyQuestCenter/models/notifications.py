"""Family Quest Center developer documentation.

File: models/notifications.py
Purpose: Provides database access and domain operations for notifications data.

Maintenance notes:
- Preserve tenant and family data isolation when changing queries.
- Keep route, template, and schema changes synchronized.
- Run regression tests before release packaging.
Documentation updated: 2026-07-31.
"""

from database import get_db
from services.tenant_context import get_current_family_id


def ensure_notification_tables():
    """Handle the ensure notification tables workflow."""
    db = get_db()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS notification_dismissals (
            notification_key TEXT PRIMARY KEY,
            family_id INTEGER,
            dismissed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    columns = {row["name"] for row in db.execute("PRAGMA table_info(notification_dismissals)").fetchall()}
    if "family_id" not in columns:
        db.execute("ALTER TABLE notification_dismissals ADD COLUMN family_id INTEGER")
    db.execute("CREATE INDEX IF NOT EXISTS idx_notification_dismissals_family_id ON notification_dismissals(family_id)")
    db.commit()


def _dismissed_keys():
    """Handle the dismissed keys workflow."""
    ensure_notification_tables()
    db = get_db()
    return {row["notification_key"] for row in db.execute("SELECT notification_key FROM notification_dismissals WHERE family_id=?", (get_current_family_id(),))}


def get_parent_notifications():
    """Build actionable parent notifications and omit dismissed items."""
    db = get_db()
    dismissed = _dismissed_keys()
    items = []

    for row in db.execute(
        """
        SELECT a.id, a.completed_at, c.title, u.name AS child_name
        FROM assignments a
        JOIN chores c ON c.id = a.chore_id
        JOIN users u ON u.id = a.child_id
        WHERE a.status = 'completed' AND c.approval_required = 1
          AND a.family_id = ? AND c.family_id = ? AND u.family_id = ?
        ORDER BY a.completed_at ASC
        """,
        (get_current_family_id(), get_current_family_id(), get_current_family_id()),
    ):
        key = f"quest_approval:{row['id']}"
        if key not in dismissed:
            items.append({
                "key": key,
                "icon": "⏳",
                "title": "Quest awaiting approval",
                "message": f"{row['child_name']} completed {row['title']}.",
                "created_at": row["completed_at"],
                "url_endpoint": "approvals.queue",
            })

    for row in db.execute(
        """
        SELECT rr.id, rr.requested_at, r.name, u.name AS child_name
        FROM reward_requests rr
        JOIN rewards r ON r.id = rr.reward_id
        JOIN users u ON u.id = rr.child_id
        WHERE rr.status = 'pending'
          AND rr.family_id = ? AND r.family_id = ? AND u.family_id = ?
        ORDER BY rr.requested_at ASC
        """,
        (get_current_family_id(), get_current_family_id(), get_current_family_id()),
    ):
        key = f"reward_request:{row['id']}"
        if key not in dismissed:
            items.append({
                "key": key,
                "icon": "🎁",
                "title": "Reward request pending",
                "message": f"{row['child_name']} requested {row['name']}.",
                "created_at": row["requested_at"],
                "url_endpoint": "rewards.requests_queue",
            })

    try:
        from services.content_packs import list_pending_pack_requests
        for row in list_pending_pack_requests():
            key = f"pack_request:{row['id']}"
            if key not in dismissed:
                items.append({
                    "key": key,
                    "icon": "📦",
                    "title": "Pack request pending",
                    "message": f"{row['child_name']} requested {row['title']}.",
                    "created_at": row["requested_at"],
                    "url_endpoint": "approvals.queue",
                })
    except Exception:
        # Notification rendering must not block the parent shell during a schema upgrade.
        pass

    items.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    return items


def dismiss_notification(notification_key: str):
    """Handle the dismiss notification workflow."""
    ensure_notification_tables()
    db = get_db()
    db.execute(
        "INSERT INTO notification_dismissals (notification_key, family_id, dismissed_at) VALUES (?, ?, CURRENT_TIMESTAMP) ON CONFLICT(notification_key, family_id) DO UPDATE SET dismissed_at=excluded.dismissed_at",
        (notification_key, get_current_family_id()),
    )
    db.commit()


def dismiss_all_notifications(keys):
    """Handle the dismiss all notifications workflow."""
    ensure_notification_tables()
    db = get_db()
    db.executemany(
        "INSERT INTO notification_dismissals (notification_key, family_id, dismissed_at) VALUES (?, ?, CURRENT_TIMESTAMP) ON CONFLICT(notification_key, family_id) DO UPDATE SET dismissed_at=excluded.dismissed_at",
        [(key, get_current_family_id()) for key in keys],
    )
    db.commit()
