"""Family Quest Center developer documentation.

File: models/chores.py
Purpose: Provides database access and domain operations for chores data.

Maintenance notes:
- Preserve tenant and family data isolation when changing queries.
- Keep route, template, and schema changes synchronized.
- Run regression tests before release packaging.
Documentation updated: 2026-07-31.
"""

from database import get_db
from services.tenant_context import get_current_family_id

FIELDS="id,title,description,difficulty,stars,approval_required,active,created_at"

def get_all_chores():
    """Retrieve all chores."""
    return get_db().execute(
        f"SELECT {FIELDS} FROM chores WHERE family_id=? ORDER BY active DESC,title ASC",
        (get_current_family_id(),),
    ).fetchall()

def create_chore(title,description,difficulty,stars,approval_required):
    """Create chore."""
    db=get_db(); db.execute(
        "INSERT INTO chores(title,description,difficulty,stars,approval_required,family_id) VALUES(?,?,?,?,?,?)",
        (title,description,difficulty,stars,int(approval_required),get_current_family_id()),
    ); db.commit()

def get_chore(chore_id):
    """Retrieve chore."""
    return get_db().execute(
        f"SELECT {FIELDS} FROM chores WHERE id=? AND family_id=?",
        (chore_id,get_current_family_id()),
    ).fetchone()

def update_chore(chore_id,title,description,difficulty,stars,approval_required):
    """Update chore."""
    db=get_db(); db.execute(
        "UPDATE chores SET title=?,description=?,difficulty=?,stars=?,approval_required=? WHERE id=? AND family_id=?",
        (title,description,difficulty,stars,int(approval_required),chore_id,get_current_family_id()),
    ); db.commit()

def set_chore_active(chore_id,active):
    """Handle the set chore active workflow."""
    fid=get_current_family_id(); db=get_db(); db.execute(
        "UPDATE chores SET active=? WHERE id=? AND family_id=?",(int(active),chore_id,fid))
    if not active:
        db.execute("UPDATE assignments SET status='cancelled' WHERE chore_id=? AND family_id=? AND status IN ('assigned','completed')",(chore_id,fid))
        db.execute("UPDATE quest_schedules SET active=0 WHERE chore_id=? AND family_id=?",(chore_id,fid))
    db.commit()

def duplicate_chore(chore_id):
    """Handle the duplicate chore workflow."""
    fid=get_current_family_id(); db=get_db(); row=db.execute(
        "SELECT title,description,difficulty,stars,approval_required FROM chores WHERE id=? AND family_id=?",
        (chore_id,fid)).fetchone()
    if not row: return False
    db.execute("INSERT INTO chores(title,description,difficulty,stars,approval_required,active,family_id) VALUES(?,?,?,?,?,1,?)",
        (f"{row['title']} (Copy)",row['description'],row['difficulty'],row['stars'],row['approval_required'],fid))
    db.commit(); return True
