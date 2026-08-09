"""Version 2 Growth System: Journeys, Adventures, and child progress."""
from datetime import date
from database import get_db
from services.tenant_context import get_current_family_id


def ensure_journey_tables():
    """Handle the ensure journey tables workflow."""
    db = get_db()
    db.executescript("""
    CREATE TABLE IF NOT EXISTS journeys (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
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
    CREATE TABLE IF NOT EXISTS adventures_v2 (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        description TEXT,
        bonus_xp INTEGER NOT NULL DEFAULT 100 CHECK(bonus_xp >= 0),
        approval_required INTEGER NOT NULL DEFAULT 1 CHECK(approval_required IN (0,1)),
        active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        family_id INTEGER
    );
    CREATE TABLE IF NOT EXISTS adventure_journeys (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        adventure_id INTEGER NOT NULL,
        journey_id INTEGER NOT NULL,
        step_order INTEGER NOT NULL,
        FOREIGN KEY(adventure_id) REFERENCES adventures_v2(id),
        FOREIGN KEY(journey_id) REFERENCES journeys(id),
        UNIQUE(adventure_id, step_order)
    );
    CREATE TABLE IF NOT EXISTS adventure_instances_v2 (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        adventure_id INTEGER NOT NULL,
        child_id INTEGER NOT NULL,
        start_date TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','completed','cancelled')),
        completed_at TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        family_id INTEGER,
        FOREIGN KEY(adventure_id) REFERENCES adventures_v2(id),
        FOREIGN KEY(child_id) REFERENCES users(id)
    );
    CREATE TABLE IF NOT EXISTS journey_instances (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        adventure_instance_id INTEGER NOT NULL,
        journey_id INTEGER NOT NULL,
        step_order INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'locked' CHECK(status IN ('locked','assigned','completed')),
        pending_approval INTEGER NOT NULL DEFAULT 0 CHECK(pending_approval IN (0,1)),
        submitted_at TEXT,
        completed_at TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(adventure_instance_id) REFERENCES adventure_instances_v2(id),
        FOREIGN KEY(journey_id) REFERENCES journeys(id),
        UNIQUE(adventure_instance_id, step_order)
    );
    """)
    columns = {row["name"] for row in db.execute("PRAGMA table_info(journey_instances)").fetchall()}
    if "pending_approval" not in columns:
        db.execute("ALTER TABLE journey_instances ADD COLUMN pending_approval INTEGER NOT NULL DEFAULT 0")
    if "submitted_at" not in columns:
        db.execute("ALTER TABLE journey_instances ADD COLUMN submitted_at TEXT")

    # Sprint 3.0-G.0.3: keep the dynamically-created Journey tables aligned
    # with the hosted multi-family schema. SQLite CREATE TABLE IF NOT EXISTS
    # does not add new columns to tables that already exist.
    for table in ("journeys", "adventures_v2", "adventure_instances_v2"):
        table_columns = {row["name"] for row in db.execute(f"PRAGMA table_info({table})").fetchall()}
        if "family_id" not in table_columns:
            db.execute(f"ALTER TABLE {table} ADD COLUMN family_id INTEGER")

    adventure_columns = {row["name"] for row in db.execute("PRAGMA table_info(adventures_v2)").fetchall()}
    if "approval_required" not in adventure_columns:
        db.execute("ALTER TABLE adventures_v2 ADD COLUMN approval_required INTEGER NOT NULL DEFAULT 1")

    adventure_instance_columns = {row["name"] for row in db.execute("PRAGMA table_info(adventure_instances_v2)").fetchall()}
    if "pending_approval" not in adventure_instance_columns:
        db.execute("ALTER TABLE adventure_instances_v2 ADD COLUMN pending_approval INTEGER NOT NULL DEFAULT 0")
    if "submitted_at" not in adventure_instance_columns:
        db.execute("ALTER TABLE adventure_instances_v2 ADD COLUMN submitted_at TEXT")
    if "parent_message" not in adventure_instance_columns:
        db.execute("ALTER TABLE adventure_instances_v2 ADD COLUMN parent_message TEXT")

    family_id = get_current_family_id()
    # Backfill records created by the clean initializer before family_id was added.
    db.execute("UPDATE adventure_instances_v2 SET family_id=(SELECT family_id FROM users WHERE users.id=adventure_instances_v2.child_id) WHERE family_id IS NULL")
    db.execute("UPDATE adventures_v2 SET family_id=? WHERE family_id IS NULL", (family_id,))
    db.execute("UPDATE journeys SET family_id=? WHERE family_id IS NULL", (family_id,))
    db.execute("CREATE INDEX IF NOT EXISTS idx_journeys_family_id ON journeys(family_id)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_adventures_v2_family_id ON adventures_v2(family_id)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_adventure_instances_v2_family_id ON adventure_instances_v2(family_id)")
    # Adventure Chapters are progression steps. XP is awarded only once through
    # the Adventure completion bonus; legacy Chapter scoring fields are reset.
    db.execute(
        """UPDATE journeys SET xp_reward=0,difficulty=1,estimated_minutes=NULL
           WHERE family_id=? AND id IN (SELECT journey_id FROM adventure_journeys)""",
        (family_id,),
    )
    db.commit()


def list_journeys(include_archived=False):
    """Handle the list journeys workflow."""
    ensure_journey_tables(); db=get_db()
    family_id=get_current_family_id()
    sql="SELECT * FROM journeys WHERE family_id=?" + ("" if include_archived else " AND active=1") + " ORDER BY active DESC, name COLLATE NOCASE"
    return db.execute(sql,(family_id,)).fetchall()


def get_journey(journey_id):
    """Retrieve journey."""
    ensure_journey_tables(); db=get_db(); return db.execute("SELECT * FROM journeys WHERE id=? AND family_id=?",(journey_id,get_current_family_id())).fetchone()


def create_journey(name, description, xp_reward, difficulty, estimated_minutes=None):
    """Create journey."""
    ensure_journey_tables(); db=get_db()
    cur=db.execute("INSERT INTO journeys(name,description,xp_reward,difficulty,estimated_minutes,family_id) VALUES(?,?,?,?,?,?)",
                   (name,description,xp_reward,difficulty,estimated_minutes,get_current_family_id())); db.commit(); return cur.lastrowid


def update_journey(journey_id,name,description,xp_reward,difficulty,estimated_minutes=None):
    """Update journey."""
    db=get_db(); db.execute("UPDATE journeys SET name=?,description=?,xp_reward=?,difficulty=?,estimated_minutes=?,updated_at=CURRENT_TIMESTAMP WHERE id=? AND family_id=?",
        (name,description,xp_reward,difficulty,estimated_minutes,journey_id,get_current_family_id())); db.commit()


def set_journey_active(journey_id,active):
    """Handle the set journey active workflow."""
    ensure_journey_tables(); db=get_db(); db.execute("UPDATE journeys SET active=?,updated_at=CURRENT_TIMESTAMP WHERE id=? AND family_id=?",(1 if active else 0,journey_id,get_current_family_id())); db.commit()


def list_adventures(include_archived=False):
    """Handle the list adventures workflow."""
    ensure_journey_tables(); db=get_db()
    where="WHERE a.family_id=?" + ("" if include_archived else " AND a.active=1")
    rows=db.execute(f"""SELECT a.*, COUNT(aj.id) journey_count FROM adventures_v2 a
        LEFT JOIN adventure_journeys aj ON aj.adventure_id=a.id {where}
        GROUP BY a.id ORDER BY a.active DESC,a.name COLLATE NOCASE""",(get_current_family_id(),)).fetchall()
    result=[]
    for row in rows:
        item=dict(row)
        item['journeys']=db.execute("""SELECT aj.id link_id,aj.step_order,j.* FROM adventure_journeys aj
            JOIN journeys j ON j.id=aj.journey_id WHERE aj.adventure_id=? ORDER BY aj.step_order""",(row['id'],)).fetchall()
        result.append(item)
    return result


def get_active_adventure_assignment_summaries() -> dict[int, list[dict]]:
    """Return active Adventure assignments grouped by Adventure ID."""
    ensure_journey_tables()
    rows = get_db().execute(
        """
        SELECT
            ai.adventure_id,
            ai.id AS instance_id,
            ai.start_date,
            u.name AS child_name,
            COUNT(ji.id) AS total_chapters,
            SUM(CASE WHEN ji.status = 'completed' THEN 1 ELSE 0 END) AS completed_chapters
        FROM adventure_instances_v2 ai
        JOIN users u
            ON u.id = ai.child_id
           AND u.family_id = ai.family_id
        LEFT JOIN journey_instances ji
            ON ji.adventure_instance_id = ai.id
        WHERE ai.family_id = ?
          AND ai.status = 'active'
          AND u.active = 1
        GROUP BY ai.id
        ORDER BY u.name COLLATE NOCASE, ai.created_at
        """,
        (get_current_family_id(),),
    ).fetchall()

    summaries: dict[int, list[dict]] = {}
    for row in rows:
        item = dict(row)
        completed = int(item.get("completed_chapters") or 0)
        total = int(item.get("total_chapters") or 0)
        item["current_chapter"] = min(completed + 1, total) if total else 0
        summaries.setdefault(item["adventure_id"], []).append(item)
    return summaries


def _normalize_chapters(chapters):
    """Return validated chapter dictionaries in display order."""
    cleaned=[]
    for chapter in chapters:
        name=(chapter.get('name') or '').strip()
        if not name:
            continue
        cleaned.append({
            'id': chapter.get('id'),
            'name': name,
            'description': (chapter.get('description') or '').strip(),
        })
    return cleaned


def create_adventure_with_chapters(name, description, bonus_xp, chapters, approval_required=True):
    """Create one Adventure and its ordered Chapters in a single transaction."""
    ensure_journey_tables(); db=get_db(); family_id=get_current_family_id()
    chapters=_normalize_chapters(chapters)
    if not chapters:
        raise ValueError('An Adventure needs at least one Chapter.')
    cur=db.execute(
        "INSERT INTO adventures_v2(name,description,bonus_xp,approval_required,family_id) VALUES(?,?,?,?,?)",
        (name,description,bonus_xp,int(bool(approval_required)),family_id),
    )
    adventure_id=cur.lastrowid
    for order,chapter in enumerate(chapters,1):
        jcur=db.execute(
            """INSERT INTO journeys(name,description,xp_reward,difficulty,estimated_minutes,family_id)
               VALUES(?,?,?,?,?,?)""",
            (chapter['name'],chapter['description'],0,1,None,family_id),
        )
        db.execute(
            "INSERT INTO adventure_journeys(adventure_id,journey_id,step_order) VALUES(?,?,?)",
            (adventure_id,jcur.lastrowid,order),
        )
    db.commit(); return adventure_id


def create_adventure(name,description,bonus_xp,journey_ids):
    """Legacy compatibility helper for pre-redesign callers."""
    ensure_journey_tables(); db=get_db()
    cur=db.execute("INSERT INTO adventures_v2(name,description,bonus_xp,family_id) VALUES(?,?,?,?)",(name,description,bonus_xp,get_current_family_id())); aid=cur.lastrowid
    _replace_adventure_journeys(db, aid, journey_ids)
    db.commit(); return aid


def get_adventure(adventure_id):
    """Retrieve adventure."""
    ensure_journey_tables(); db=get_db()
    row=db.execute("SELECT * FROM adventures_v2 WHERE id=? AND family_id=?",(adventure_id,get_current_family_id())).fetchone()
    if not row: return None
    item=dict(row)
    item['journeys']=db.execute("""SELECT aj.id link_id,aj.step_order,j.* FROM adventure_journeys aj
        JOIN journeys j ON j.id=aj.journey_id WHERE aj.adventure_id=? AND j.family_id=? ORDER BY aj.step_order""",(adventure_id,get_current_family_id())).fetchall()
    return item



def adventure_has_assignments(adventure_id):
    """Return True once an Adventure has ever been assigned in this family."""
    ensure_journey_tables(); db=get_db()
    row=db.execute(
        "SELECT 1 FROM adventure_instances_v2 WHERE adventure_id=? AND family_id=? LIMIT 1",
        (adventure_id,get_current_family_id()),
    ).fetchone()
    return row is not None


def duplicate_adventure(adventure_id):
    """Create an editable family-owned copy of an Adventure template."""
    source=get_adventure(adventure_id)
    if not source:
        return None
    chapters=[
        {'name': row['name'], 'description': row['description'] or ''}
        for row in source['journeys']
    ]
    base_name=f"{source['name']} Copy"
    return create_adventure_with_chapters(
        base_name, source['description'] or '', int(source['bonus_xp'] or 0), chapters,
        bool(source.get('approval_required', 1)),
    )

def _replace_adventure_journeys(db, adventure_id, journey_ids):
    """Handle the replace adventure journeys workflow."""
    db.execute("DELETE FROM adventure_journeys WHERE adventure_id=?",(adventure_id,))
    for order,jid in enumerate(journey_ids,1):
        db.execute("INSERT INTO adventure_journeys(adventure_id,journey_id,step_order) VALUES(?,?,?)",(adventure_id,jid,order))


def update_adventure_with_chapters(adventure_id, name, description, bonus_xp, chapters, approval_required=True):
    """Update Adventure details and ordered Chapters when no assignment is active."""
    ensure_journey_tables(); db=get_db(); family_id=get_current_family_id()
    chapters=_normalize_chapters(chapters)
    if not chapters:
        raise ValueError('An Adventure needs at least one Chapter.')
    active_instances=db.execute(
        "SELECT COUNT(*) FROM adventure_instances_v2 WHERE adventure_id=? AND status='active' AND family_id=?",
        (adventure_id,family_id),
    ).fetchone()[0]
    if active_instances:
        return False
    db.execute(
        "UPDATE adventures_v2 SET name=?,description=?,bonus_xp=?,approval_required=?,updated_at=CURRENT_TIMESTAMP WHERE id=? AND family_id=?",
        (name,description,bonus_xp,int(bool(approval_required)),adventure_id,family_id),
    )
    existing={row['id']:row for row in db.execute(
        """SELECT j.* FROM adventure_journeys aj JOIN journeys j ON j.id=aj.journey_id
           WHERE aj.adventure_id=? AND j.family_id=?""",(adventure_id,family_id)
    ).fetchall()}
    db.execute("DELETE FROM adventure_journeys WHERE adventure_id=?",(adventure_id,))
    for order,chapter in enumerate(chapters,1):
        chapter_id=chapter.get('id')
        if chapter_id and int(chapter_id) in existing:
            chapter_id=int(chapter_id)
            db.execute(
                """UPDATE journeys SET name=?,description=?,xp_reward=?,difficulty=?,estimated_minutes=?,updated_at=CURRENT_TIMESTAMP
                   WHERE id=? AND family_id=?""",
                (chapter['name'],chapter['description'],0,1,None,chapter_id,family_id),
            )
        else:
            cur=db.execute(
                """INSERT INTO journeys(name,description,xp_reward,difficulty,estimated_minutes,family_id)
                   VALUES(?,?,?,?,?,?)""",
                (chapter['name'],chapter['description'],0,1,None,family_id),
            )
            chapter_id=cur.lastrowid
        db.execute(
            "INSERT INTO adventure_journeys(adventure_id,journey_id,step_order) VALUES(?,?,?)",
            (adventure_id,chapter_id,order),
        )
    db.commit(); return True


def update_adventure(adventure_id,name,description,bonus_xp,journey_ids):
    """Legacy compatibility helper."""
    ensure_journey_tables(); db=get_db()
    active_instances=db.execute("SELECT COUNT(*) FROM adventure_instances_v2 WHERE adventure_id=? AND status='active' AND family_id=?",(adventure_id,get_current_family_id())).fetchone()[0]
    if active_instances:
        return False
    db.execute("UPDATE adventures_v2 SET name=?,description=?,bonus_xp=?,updated_at=CURRENT_TIMESTAMP WHERE id=? AND family_id=?",(name,description,bonus_xp,adventure_id,get_current_family_id()))
    _replace_adventure_journeys(db,adventure_id,journey_ids)
    db.commit(); return True


def set_adventure_active(adventure_id,active):
    """Handle the set adventure active workflow."""
    db=get_db(); db.execute("UPDATE adventures_v2 SET active=?,updated_at=CURRENT_TIMESTAMP WHERE id=? AND family_id=?",(1 if active else 0,adventure_id,get_current_family_id())); db.commit()


def assign_adventure(adventure_id,child_id,start_date=None):
    """Handle the assign adventure workflow."""
    ensure_journey_tables(); db=get_db(); family_id=get_current_family_id(); start_date=start_date or date.today().isoformat()
    adventure=db.execute("SELECT id FROM adventures_v2 WHERE id=? AND family_id=? AND active=1",(adventure_id,family_id)).fetchone()
    child=db.execute("SELECT id FROM users WHERE id=? AND family_id=? AND role='child' AND active=1",(child_id,family_id)).fetchone()
    if not adventure or not child:
        raise ValueError('The Adventure or child is not available for this family.')
    duplicate=db.execute(
        "SELECT id FROM adventure_instances_v2 WHERE adventure_id=? AND child_id=? AND family_id=? AND status='active'",
        (adventure_id,child_id,family_id),
    ).fetchone()
    if duplicate:
        return duplicate['id']
    steps=db.execute("""SELECT aj.journey_id,aj.step_order FROM adventure_journeys aj
        JOIN journeys j ON j.id=aj.journey_id
        WHERE aj.adventure_id=? AND j.family_id=? ORDER BY aj.step_order""",(adventure_id,family_id)).fetchall()
    if not steps:
        raise ValueError('This Adventure has no Chapters.')
    cur=db.execute("INSERT INTO adventure_instances_v2(adventure_id,child_id,start_date,family_id) VALUES(?,?,?,?)",(adventure_id,child_id,start_date,family_id)); iid=cur.lastrowid
    for index,step in enumerate(steps):
        db.execute("INSERT INTO journey_instances(adventure_instance_id,journey_id,step_order,status) VALUES(?,?,?,?)",
                   (iid,step['journey_id'],step['step_order'],'assigned' if index==0 else 'locked'))
    db.commit(); return iid


def assign_adventure_to_children(adventure_id, child_ids, start_date=None):
    """Handle the assign adventure to children workflow."""
    assigned=[]
    for child_id in child_ids:
        assigned.append(assign_adventure(adventure_id,int(child_id),start_date))
    return assigned

def cancel_adventure_instance(instance_id):
    """Cancel one active child Adventure while preserving Chapter history."""
    ensure_journey_tables(); db=get_db(); family_id=get_current_family_id()
    cursor=db.execute(
        """UPDATE adventure_instances_v2
           SET status='cancelled', pending_approval=0, parent_message=NULL
           WHERE id=? AND family_id=? AND status='active'""",
        (instance_id,family_id),
    )
    if cursor.rowcount:
        db.execute(
            """UPDATE journey_instances
               SET pending_approval=0, submitted_at=NULL
               WHERE adventure_instance_id=?""",
            (instance_id,),
        )
    db.commit(); return cursor.rowcount > 0


def current_child_journeys(child_id):
    """Handle the current child journeys workflow."""
    ensure_journey_tables(); db=get_db()
    return db.execute("""SELECT ji.id,ji.step_order,ji.status,COALESCE(ji.pending_approval,0) pending_approval,j.name title,j.name chapter_name,j.description,
        ai.id adventure_instance_id,a.name adventure_name,a.description adventure_description,a.bonus_xp,
        (SELECT COUNT(*) FROM journey_instances x WHERE x.adventure_instance_id=ai.id) total_steps
        FROM journey_instances ji JOIN journeys j ON j.id=ji.journey_id
        JOIN adventure_instances_v2 ai ON ai.id=ji.adventure_instance_id
        JOIN adventures_v2 a ON a.id=ai.adventure_id
        WHERE ai.child_id=? AND ai.family_id=? AND a.family_id=? AND j.family_id=? AND ai.status='active' AND ji.status='assigned'
        ORDER BY ai.created_at,ji.step_order""",(child_id,get_current_family_id(),get_current_family_id(),get_current_family_id())).fetchall()



def list_child_completed_journeys_today(child_id):
    """Return Adventure Chapters the child completed today, newest first."""
    ensure_journey_tables(); db=get_db(); family_id=get_current_family_id()
    return db.execute(
        """SELECT ji.id,ji.step_order,ji.completed_at,j.name title,j.description,
                  ai.id adventure_instance_id,a.name adventure_name,a.bonus_xp,
                  (SELECT COUNT(*) FROM journey_instances x WHERE x.adventure_instance_id=ai.id) total_steps
           FROM journey_instances ji
           JOIN journeys j ON j.id=ji.journey_id
           JOIN adventure_instances_v2 ai ON ai.id=ji.adventure_instance_id
           JOIN adventures_v2 a ON a.id=ai.adventure_id
           WHERE ai.child_id=? AND ai.family_id=? AND a.family_id=? AND j.family_id=?
             AND ji.status='completed' AND date(ji.completed_at)=date('now','localtime')
           ORDER BY datetime(ji.completed_at) DESC,ji.id DESC""",
        (child_id,family_id,family_id,family_id),
    ).fetchall()

def get_journey_instance(instance_id):
    """Retrieve journey instance."""
    ensure_journey_tables(); db=get_db()
    family_id=get_current_family_id()
    row=db.execute("""SELECT ji.*,j.name title,j.description,j.xp_reward,j.difficulty,j.estimated_minutes,
        ai.child_id,ai.adventure_id,a.name adventure_name,a.bonus_xp,
        a.approval_required,u.name child_name
        FROM journey_instances ji JOIN journeys j ON j.id=ji.journey_id
        JOIN adventure_instances_v2 ai ON ai.id=ji.adventure_instance_id
        JOIN adventures_v2 a ON a.id=ai.adventure_id JOIN users u ON u.id=ai.child_id
        WHERE ji.id=? AND ai.family_id=? AND a.family_id=? AND j.family_id=? AND u.family_id=?""",
        (instance_id,family_id,family_id,family_id,family_id)).fetchone()
    return dict(row) if row else None


def complete_journey_instance(instance_id):
    """Complete a Chapter immediately, unlock the next Chapter, or submit the Adventure for celebration."""
    ensure_journey_tables(); db=get_db(); row=get_journey_instance(instance_id)
    if not row or row['status']!='assigned':
        return None

    family_id=get_current_family_id()
    owner=db.execute(
        "SELECT id FROM adventure_instances_v2 WHERE id=? AND child_id=? AND family_id=?",
        (row['adventure_instance_id'], row['child_id'], family_id),
    ).fetchone()
    if not owner:
        return None

    db.execute(
        "UPDATE journey_instances SET status='completed',pending_approval=0,submitted_at=NULL,completed_at=CURRENT_TIMESTAMP WHERE id=?",
        (instance_id,),
    )
    nxt=db.execute(
        "SELECT id,step_order FROM journey_instances WHERE adventure_instance_id=? AND status='locked' ORDER BY step_order LIMIT 1",
        (row['adventure_instance_id'],),
    ).fetchone()
    adventure_ready=False
    next_step=None
    if nxt:
        db.execute("UPDATE journey_instances SET status='assigned',pending_approval=0 WHERE id=?",(nxt['id'],))
        next_step=nxt['step_order']
    else:
        if row.get('approval_required', 1):
            db.execute(
                "UPDATE adventure_instances_v2 SET pending_approval=1,submitted_at=CURRENT_TIMESTAMP WHERE id=? AND family_id=?",
                (row['adventure_instance_id'],family_id),
            )
        else:
            db.execute(
                """UPDATE adventure_instances_v2
                   SET status='completed',pending_approval=0,
                       submitted_at=CURRENT_TIMESTAMP,completed_at=CURRENT_TIMESTAMP
                   WHERE id=? AND family_id=?""",
                (row['adventure_instance_id'],family_id),
            )
            user=db.execute(
                "SELECT total_xp FROM users WHERE id=? AND family_id=?",
                (row['child_id'],family_id),
            ).fetchone()
            from models.progression import calculate_level
            bonus_xp=int(row['bonus_xp'] or 0)
            new_total_xp=int(user['total_xp'] or 0)+bonus_xp
            db.execute(
                "UPDATE users SET total_xp=?,current_level=? WHERE id=? AND family_id=?",
                (new_total_xp,calculate_level(new_total_xp),row['child_id'],family_id),
            )
            if bonus_xp:
                db.execute(
                    "INSERT INTO xp_history(child_id,xp,reason,family_id) VALUES(?,?,?,?)",
                    (row['child_id'],bonus_xp,f"Adventure completed: {row['adventure_name']}",family_id),
                )
            from models.achievements import check_and_award_achievements
            check_and_award_achievements(db,row['child_id'])
        adventure_ready=True
    db.commit()
    return {
        'child_id':row['child_id'],
        'title':row['title'],
        'xp_reward':0,
        'next_step':next_step,
        'adventure_ready':adventure_ready,
        'adventure_name':row['adventure_name'],
    }


def list_pending_v2_journey_approvals():
    """Legacy compatibility: Chapters no longer require approval."""
    return []


def count_pending_v2_journey_approvals():
    """Handle the count pending v2 journey approvals workflow."""
    return 0


def get_adventure_instance(instance_id):
    """Retrieve adventure instance."""
    ensure_journey_tables(); db=get_db(); family_id=get_current_family_id()
    row=db.execute(
        """SELECT ai.*,a.name title,a.name adventure_name,a.description,a.bonus_xp,
                  ai.child_id,u.name child_name,
                  (SELECT COUNT(*) FROM journey_instances ji WHERE ji.adventure_instance_id=ai.id) total_steps,
                  (SELECT COUNT(*) FROM journey_instances ji WHERE ji.adventure_instance_id=ai.id AND ji.status='completed') completed_steps
           FROM adventure_instances_v2 ai
           JOIN adventures_v2 a ON a.id=ai.adventure_id
           JOIN users u ON u.id=ai.child_id
           WHERE ai.id=? AND ai.family_id=? AND a.family_id=? AND u.family_id=?""",
        (instance_id,family_id,family_id,family_id),
    ).fetchone()
    return dict(row) if row else None


def list_pending_adventure_approvals():
    """Handle the list pending adventure approvals workflow."""
    ensure_journey_tables(); db=get_db(); family_id=get_current_family_id()
    rows=db.execute(
        """SELECT ai.id,ai.submitted_at completed_at,a.name title,a.description,a.bonus_xp xp_reward,
                  0 difficulty,0 stars,ai.child_id,u.name child_name,a.name adventure_name,
                  (SELECT COUNT(*) FROM journey_instances ji WHERE ji.adventure_instance_id=ai.id) total_steps
           FROM adventure_instances_v2 ai
           JOIN adventures_v2 a ON a.id=ai.adventure_id
           JOIN users u ON u.id=ai.child_id
           WHERE ai.pending_approval=1 AND ai.status='active'
             AND a.active=1 AND u.active=1
             AND ai.family_id=? AND a.family_id=? AND u.family_id=?
           ORDER BY datetime(ai.submitted_at),ai.id""",
        (family_id,family_id,family_id),
    ).fetchall()
    return [{**dict(row),'activity_kind':'adventure','type_label':'Adventure Celebration'} for row in rows]


def count_pending_adventure_approvals():
    """Handle the count pending adventure approvals workflow."""
    return len(list_pending_adventure_approvals())


def approve_adventure_instance(instance_id, parent_message=None):
    """Approve an Adventure and queue any earned achievements for the child."""
    ensure_journey_tables(); db=get_db(); row=get_adventure_instance(instance_id)
    if not row or row['status']!='active' or not row.get('pending_approval'):
        return None
    family_id=get_current_family_id()
    try:
        db.execute("BEGIN")
        db.execute(
            "UPDATE adventure_instances_v2 SET status='completed',pending_approval=0,completed_at=CURRENT_TIMESTAMP,parent_message=? WHERE id=? AND family_id=?",
            ((parent_message or '').strip() or None,instance_id,family_id),
        )
        user=db.execute("SELECT total_xp FROM users WHERE id=? AND family_id=?",(row['child_id'],family_id)).fetchone()
        from models.progression import calculate_level
        new_total_xp=int(user['total_xp'] or 0)+int(row['bonus_xp'] or 0)
        db.execute("UPDATE users SET total_xp=?,current_level=? WHERE id=? AND family_id=?",(new_total_xp,calculate_level(new_total_xp),row['child_id'],family_id))
        bonus_xp = int(row['bonus_xp'] or 0)
        if bonus_xp:
            db.execute(
                "INSERT INTO xp_history(child_id,xp,reason,family_id) VALUES(?,?,?,?)",
                (row['child_id'], bonus_xp, f"Adventure completed: {row['adventure_name']}", family_id),
            )
        from models.achievements import check_and_award_achievements
        unlocked=check_and_award_achievements(db,row['child_id'])
        db.commit()
        return {'child_id':row['child_id'],'adventure_name':row['adventure_name'],'bonus_xp':row['bonus_xp'],'achievements':unlocked}
    except Exception:
        db.rollback()
        raise


def return_adventure_instance(instance_id):
    """Return an Adventure celebration by reopening the final Chapter."""
    ensure_journey_tables(); db=get_db(); row=get_adventure_instance(instance_id)
    if not row or row['status']!='active' or not row.get('pending_approval'):
        return False
    final=db.execute(
        "SELECT id FROM journey_instances WHERE adventure_instance_id=? ORDER BY step_order DESC LIMIT 1",
        (instance_id,),
    ).fetchone()
    if final:
        db.execute("UPDATE journey_instances SET status='assigned',completed_at=NULL WHERE id=?",(final['id'],))
    db.execute("UPDATE adventure_instances_v2 SET pending_approval=0,submitted_at=NULL WHERE id=? AND family_id=?",(instance_id,get_current_family_id()))
    db.commit(); return True


def approve_v2_journey(instance_id):
    """Legacy compatibility; Chapter approval was removed in RC-0014."""
    return None


def return_v2_journey(instance_id):
    """Legacy compatibility; Chapter approval was removed in RC-0014."""
    return False


def list_child_adventure_celebrations(child_id):
    """Handle the list child adventure celebrations workflow."""
    ensure_journey_tables(); db=get_db(); family_id=get_current_family_id()
    return db.execute(
        """SELECT ai.id,a.name adventure_name,a.description adventure_description,a.bonus_xp,
                  ai.pending_approval,ai.status,ai.parent_message,
                  (SELECT COUNT(*) FROM journey_instances ji WHERE ji.adventure_instance_id=ai.id) total_steps
           FROM adventure_instances_v2 ai
           JOIN adventures_v2 a ON a.id=ai.adventure_id
           WHERE ai.child_id=? AND ai.family_id=? AND a.family_id=?
             AND (ai.pending_approval=1 OR ai.status='completed')
           ORDER BY COALESCE(ai.completed_at,ai.submitted_at) DESC""",
        (child_id,family_id,family_id),
    ).fetchall()

def active_adventure_count():
    """Handle the active adventure count workflow."""
    ensure_journey_tables()
    return get_db().execute(
        "SELECT COUNT(*) FROM adventure_instances_v2 WHERE status='active' AND family_id=?",
        (get_current_family_id(),),
    ).fetchone()[0]

