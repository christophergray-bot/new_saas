"""Tenant-isolated Archive Center routes."""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from database import get_db
from models.administration import log_audit
from services.tenant_context import get_current_family_id

archive_blueprint = Blueprint("archive", __name__, url_prefix="/parent/archive")
ARCHIVE_TYPES = {
    "children": {"title": "Family Members", "icon": "👦", "description": "Archived child profiles and preserved family history."},
    "quests": {"title": "Quests", "icon": "📜", "description": "Reusable quests removed from active assignment lists."},
    "adventures": {"title": "Adventures", "icon": "🗺️", "description": "Archived adventure templates and their completed history."},
    "challenges": {"title": "Challenges", "icon": "⭐", "description": "Past family challenges that are no longer active."},
    "rewards": {"title": "Rewards", "icon": "🎁", "description": "Archived rewards and reward categories."},
    "schedules": {"title": "Schedules", "icon": "📅", "description": "Archived quest schedules."},
}

def _archive_rows(kind, search=""):
    db, family_id = get_db(), get_current_family_id()
    term = f"%{search.lower()}%"
    if kind == "children":
        return db.execute("""SELECT id,name AS title,'Child Profile' AS subtitle,created_at,'child' AS record_type
            FROM users WHERE role='child' AND active=0 AND family_id=? AND LOWER(name) LIKE ? ORDER BY name""", (family_id, term)).fetchall()
    if kind == "quests":
        return db.execute("""SELECT id,title,COALESCE(description,'') AS subtitle,created_at,'quest' AS record_type
            FROM chores WHERE active=0 AND family_id=? AND (LOWER(title) LIKE ? OR LOWER(COALESCE(description,'')) LIKE ?) ORDER BY title""", (family_id, term, term)).fetchall()
    if kind == "adventures":
        return db.execute("""SELECT id,name AS title,COALESCE(description,'') AS subtitle,created_at,'adventure_v2' AS record_type
            FROM adventures_v2 WHERE active=0 AND family_id=? AND (LOWER(name) LIKE ? OR LOWER(COALESCE(description,'')) LIKE ?) ORDER BY name""", (family_id, term, term)).fetchall()
    if kind == "challenges":
        return db.execute("""SELECT id,name AS title,COALESCE(description,'') AS subtitle,created_at,'challenge' AS record_type
            FROM family_challenges WHERE active=0 AND family_id=? AND (LOWER(name) LIKE ? OR LOWER(COALESCE(description,'')) LIKE ?) ORDER BY name""", (family_id, term, term)).fetchall()
    if kind == "rewards":
        rewards = db.execute("""SELECT id,name AS title,COALESCE(description,'') AS subtitle,created_at,'reward' AS record_type
            FROM rewards WHERE active=0 AND family_id=? AND (LOWER(name) LIKE ? OR LOWER(COALESCE(description,'')) LIKE ?) ORDER BY name""", (family_id, term, term)).fetchall()
        categories = db.execute("""SELECT id,name AS title,'Reward Category' AS subtitle,created_at,'reward_category' AS record_type
            FROM reward_categories WHERE active=0 AND family_id=? AND LOWER(name) LIKE ? ORDER BY name""", (family_id, term)).fetchall()
        return list(rewards) + list(categories)
    if kind == "schedules":
        return db.execute("""SELECT s.id,c.title || ' — ' || u.name AS title,'Quest Schedule' AS subtitle,
            s.created_at,'quest_schedule' AS record_type FROM quest_schedules s
            JOIN chores c ON c.id=s.chore_id AND c.family_id=s.family_id
            JOIN users u ON u.id=s.child_id AND u.family_id=s.family_id
            WHERE s.active=0 AND s.family_id=? AND LOWER(c.title || ' ' || u.name) LIKE ? ORDER BY c.title,u.name""", (family_id, term)).fetchall()
    abort(404)

@archive_blueprint.route("/")
def center():
    return render_template("parent/archive/center.html", cards=[{**meta, "kind": kind, "count": len(_archive_rows(kind))} for kind, meta in ARCHIVE_TYPES.items()])

@archive_blueprint.route("/<kind>")
def category(kind):
    if kind not in ARCHIVE_TYPES: abort(404)
    search = request.args.get("q", "").strip()
    return render_template("parent/archive/category.html", kind=kind, meta=ARCHIVE_TYPES[kind], rows=_archive_rows(kind, search), search_query=search)

@archive_blueprint.post("/<kind>/<record_type>/<int:record_id>/restore")
def restore(kind, record_type, record_id):
    mapping = {
        "child": ("users", "Child profile"), "quest": ("chores", "Quest"),
        "adventure_v2": ("adventures_v2", "Adventure"), "challenge": ("family_challenges", "Family challenge"),
        "reward": ("rewards", "Reward"), "reward_category": ("reward_categories", "Reward category"),
        "quest_schedule": ("quest_schedules", "Quest schedule"),
    }
    if kind not in ARCHIVE_TYPES or record_type not in mapping: abort(404)
    table, label = mapping[record_type]
    db = get_db()
    family_id = get_current_family_id()
    record_name = None
    if record_type == "child":
        row = db.execute(
            "SELECT name FROM users WHERE id=? AND family_id=? AND role='child'",
            (record_id, family_id),
        ).fetchone()
        record_name = row["name"] if row else None
    cursor = db.execute(
        f"UPDATE {table} SET active=1 WHERE id=? AND family_id=?",
        (record_id, family_id),
    )
    db.commit()
    if cursor.rowcount:
        if record_type == "child":
            log_audit("child_restored", "child", record_id, record_name or "Child")
        else:
            log_audit("archive_item_restored", record_type, record_id, f"Restored from {kind} archive")
        flash(f"{label} restored.", "success")
    else:
        flash(f"{label} could not be restored.", "error")
    return redirect(url_for("archive.category", kind=kind))
