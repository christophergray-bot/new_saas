"""Quest chain templates, child instances, ordered steps, and completion bonuses."""
from datetime import date, datetime
from sqlite3 import IntegrityError
from database import get_db
from models.economy import award_stars
from models.progression import calculate_level
from services.tenant_context import get_current_family_id


def ensure_adventure_schedule_tables():
    """Create recurring-adventure support without requiring a manual migration."""
    db = get_db()
    db.executescript("""
        CREATE TABLE IF NOT EXISTS adventure_schedules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chain_id INTEGER NOT NULL,
            child_id INTEGER NOT NULL,
            schedule_type TEXT NOT NULL CHECK(schedule_type IN ('daily','weekly','monthly')),
            start_date TEXT NOT NULL,
            end_date TEXT,
            weekday INTEGER,
            day_of_month INTEGER,
            active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(chain_id) REFERENCES quest_chains(id),
            FOREIGN KEY(child_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS adventure_schedule_occurrences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            schedule_id INTEGER NOT NULL,
            occurrence_date TEXT NOT NULL,
            chain_instance_id INTEGER,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(schedule_id) REFERENCES adventure_schedules(id),
            FOREIGN KEY(chain_instance_id) REFERENCES quest_chain_instances(id),
            UNIQUE(schedule_id, occurrence_date)
        );
    """)
    db.commit()


def _schedule_matches(schedule, target_date: date) -> bool:
    """Handle the schedule matches workflow."""
    start = date.fromisoformat(schedule['start_date'])
    if target_date < start:
        return False
    if schedule['end_date'] and target_date > date.fromisoformat(schedule['end_date']):
        return False
    kind = schedule['schedule_type']
    if kind == 'daily':
        return True
    if kind == 'weekly':
        return target_date.weekday() == int(schedule['weekday'])
    if kind == 'monthly':
        return target_date.day == int(schedule['day_of_month'])
    return False


def create_adventure_schedule(chain_id: int, child_id: int, schedule_type: str, start_date: str,
                              end_date: str | None = None, weekday: int | None = None,
                              day_of_month: int | None = None):
    """Create adventure schedule."""
    ensure_adventure_schedule_tables()
    schedule_type = (schedule_type or '').lower()
    if schedule_type not in {'daily','weekly','monthly'}:
        raise ValueError('Select daily, weekly, or monthly recurrence.')
    start = date.fromisoformat(start_date)
    if end_date and date.fromisoformat(end_date) < start:
        raise ValueError('End date cannot be before the start date.')
    if schedule_type == 'weekly' and (weekday is None or weekday not in range(7)):
        raise ValueError('Select a weekday for the weekly adventure.')
    if schedule_type == 'monthly' and (day_of_month is None or not 1 <= day_of_month <= 28):
        raise ValueError('Monthly adventures must use a day from 1 through 28.')
    db=get_db()
    cur=db.execute("""INSERT INTO adventure_schedules
        (chain_id,child_id,schedule_type,start_date,end_date,weekday,day_of_month)
        VALUES(?,?,?,?,?,?,?)""",(chain_id,child_id,schedule_type,start_date,end_date,weekday,day_of_month))
    db.commit()
    return cur.lastrowid


def list_adventure_schedules(include_inactive: bool = True):
    """Handle the list adventure schedules workflow."""
    ensure_adventure_schedule_tables()
    db=get_db(); where='' if include_inactive else 'WHERE s.active=1'
    return db.execute(f"""SELECT s.*,q.name AS chain_name,u.name AS child_name
        FROM adventure_schedules s JOIN quest_chains q ON q.id=s.chain_id
        JOIN users u ON u.id=s.child_id {where}
        ORDER BY s.active DESC,q.name,u.name""").fetchall()


def set_adventure_schedule_active(schedule_id: int, active: bool):
    """Handle the set adventure schedule active workflow."""
    ensure_adventure_schedule_tables(); db=get_db()
    db.execute('UPDATE adventure_schedules SET active=? WHERE id=?',(1 if active else 0,schedule_id)); db.commit()


def generate_adventures_for_date(target_date: date | None = None):
    """Generate due adventure instances once per schedule/date."""
    ensure_adventure_schedule_tables(); selected=target_date or date.today(); due=selected.isoformat(); db=get_db()
    created=skipped=0
    schedules=db.execute('SELECT * FROM adventure_schedules WHERE active=1').fetchall()
    for schedule in schedules:
        if not _schedule_matches(schedule,selected):
            continue
        try:
            db.execute('INSERT INTO adventure_schedule_occurrences(schedule_id,occurrence_date) VALUES(?,?)',(schedule['id'],due))
            db.commit()
        except Exception:
            db.rollback(); skipped += 1; continue
        iid=assign_chain(schedule['chain_id'],schedule['child_id'],due)
        if iid:
            db.execute('UPDATE adventure_schedule_occurrences SET chain_instance_id=? WHERE schedule_id=? AND occurrence_date=?',(iid,schedule['id'],due)); db.commit(); created += 1
        else:
            db.execute('DELETE FROM adventure_schedule_occurrences WHERE schedule_id=? AND occurrence_date=?',(schedule['id'],due)); db.commit(); skipped += 1
    return {'date':due,'created':created,'skipped':skipped}


def list_chain_templates(include_archived: bool = False):
    """Handle the list chain templates workflow."""
    db=get_db()
    where="" if include_archived else "WHERE qc.active = 1"
    rows=db.execute(f"""
        SELECT qc.*, COUNT(qcs.id) AS step_count
        FROM quest_chains qc LEFT JOIN quest_chain_steps qcs ON qcs.chain_id=qc.id
        {where}
        GROUP BY qc.id ORDER BY qc.active DESC, qc.name
    """).fetchall()
    result=[]
    for row in rows:
        item=dict(row)
        item['steps']=[dict(step) for step in db.execute("""
            SELECT qcs.id,qcs.step_order,qcs.chore_id,c.title,c.active AS chore_active
            FROM quest_chain_steps qcs JOIN chores c ON c.id=qcs.chore_id
            WHERE qcs.chain_id=? ORDER BY qcs.step_order
        """,(row['id'],)).fetchall()]
        result.append(item)
    return result


def get_chain_template(chain_id: int):
    """Retrieve chain template."""
    db=get_db()
    chain=db.execute("SELECT * FROM quest_chains WHERE id=?",(chain_id,)).fetchone()
    if not chain: return None, []
    steps=db.execute("""
        SELECT qcs.*, c.title, c.description, c.stars, c.approval_required
        FROM quest_chain_steps qcs JOIN chores c ON c.id=qcs.chore_id
        WHERE qcs.chain_id=? AND c.active=1 ORDER BY qcs.step_order
    """,(chain_id,)).fetchall()
    return chain, steps


def create_chain(name, description, bonus_xp, bonus_stars, ordered, chore_ids):
    """Create chain."""
    db=get_db(); now=datetime.now().isoformat()
    cur=db.execute("""INSERT INTO quest_chains(name,description,bonus_xp,bonus_stars,ordered_steps,created_at)
                      VALUES(?,?,?,?,?,?)""",(name,description,bonus_xp,bonus_stars,1 if ordered else 0,now))
    chain_id=cur.lastrowid
    for order,chore_id in enumerate(chore_ids,1):
        db.execute("INSERT INTO quest_chain_steps(chain_id,chore_id,step_order) VALUES(?,?,?)",(chain_id,chore_id,order))
    db.commit(); return chain_id


def set_chain_active(chain_id:int, active:bool):
    """Archive/restore an adventure and remove unfinished archived work from gameplay."""
    db=get_db()
    db.execute("UPDATE quest_chains SET active=? WHERE id=?",(1 if active else 0,chain_id))
    if not active:
        ensure_adventure_schedule_tables()
        db.execute("UPDATE adventure_schedules SET active=0 WHERE chain_id=?",(chain_id,))
        instance_ids=[r['id'] for r in db.execute(
            "SELECT id FROM quest_chain_instances WHERE chain_id=? AND status='active'",(chain_id,)
        ).fetchall()]
        if instance_ids:
            marks=','.join('?' for _ in instance_ids)
            db.execute(f"UPDATE assignments SET status='cancelled' WHERE chain_instance_id IN ({marks}) AND status IN ('assigned','completed')",instance_ids)
            db.execute(f"UPDATE quest_chain_instances SET status='archived' WHERE id IN ({marks})",instance_ids)
    db.commit()


def move_chain_step(chain_id:int, step_id:int, direction:str) -> bool:
    """Move an adventure step up or down while keeping contiguous order."""
    if direction not in {'up','down'}:
        return False
    db=get_db()
    current=db.execute("SELECT id,step_order FROM quest_chain_steps WHERE id=? AND chain_id=?",(step_id,chain_id)).fetchone()
    if not current:
        return False
    operator='<' if direction=='up' else '>'
    ordering='DESC' if direction=='up' else 'ASC'
    neighbor=db.execute(f"SELECT id,step_order FROM quest_chain_steps WHERE chain_id=? AND step_order {operator} ? ORDER BY step_order {ordering} LIMIT 1",(chain_id,current['step_order'])).fetchone()
    if not neighbor:
        return False
    db.execute("UPDATE quest_chain_steps SET step_order=-1 WHERE id=?",(current['id'],))
    db.execute("UPDATE quest_chain_steps SET step_order=? WHERE id=?",(current['step_order'],neighbor['id']))
    db.execute("UPDATE quest_chain_steps SET step_order=? WHERE id=?",(neighbor['step_order'],current['id']))
    db.commit()
    return True




def ensure_assignment_uniqueness_index():
    """Keep daily quests unique without blocking adventure steps.

    Older Version 1.0 databases used a broad unique index on
    (chore_id, child_id, due_date). That index also covered adventure
    assignments and caused the entire adventure transaction to roll back
    whenever a child already had the same quest as a daily mission.
    """
    db = get_db()
    db.execute("DROP INDEX IF EXISTS assignments_unique_daily")
    db.execute(
        """CREATE UNIQUE INDEX IF NOT EXISTS assignments_unique_daily
           ON assignments(chore_id, child_id, due_date)
           WHERE chain_instance_id IS NULL"""
    )
    db.commit()


def assign_chain(chain_id:int, child_id:int, due_date:str|None=None):
    """Assign an adventure as one child-specific instance.

    A child may already have one of the same quests assigned as a daily mission.
    That must not prevent the adventure from being assigned. Duplicate adventure
    instances are prevented by chain, child, due date, and active status instead.
    """
    ensure_assignment_uniqueness_index()
    db=get_db(); chain,steps=get_chain_template(chain_id)
    if not chain or not steps or not chain['active']:
        return None
    due_date=due_date or date.today().isoformat(); now=datetime.now().isoformat()

    existing_instance=db.execute(
        """SELECT id FROM quest_chain_instances
             WHERE chain_id=? AND child_id=? AND due_date=? AND status='active'
             LIMIT 1""",
        (chain_id,child_id,due_date),
    ).fetchone()
    if existing_instance:
        return None

    try:
        cur=db.execute("""INSERT INTO quest_chain_instances(chain_id,child_id,status,started_at,due_date)
                          VALUES(?,?,'active',?,?)""",(chain_id,child_id,now,due_date))
        instance_id=cur.lastrowid
        for step in steps:
            db.execute("""INSERT INTO assignments(chore_id,child_id,due_date,status,chain_instance_id,chain_step_id)
                          VALUES(?,?,?,'assigned',?,?)""",(step['chore_id'],child_id,due_date,instance_id,step['id']))
        db.commit()
        return instance_id
    except IntegrityError:
        db.rollback()
        return None


def can_complete_chain_assignment(assignment_id:int):
    """Handle the can complete chain assignment workflow."""
    db=get_db(); row=db.execute("""
      SELECT a.chain_instance_id,a.chain_step_id,qc.ordered_steps,qcs.step_order
      FROM assignments a LEFT JOIN quest_chain_instances qci ON qci.id=a.chain_instance_id
      LEFT JOIN quest_chains qc ON qc.id=qci.chain_id LEFT JOIN quest_chain_steps qcs ON qcs.id=a.chain_step_id
      WHERE a.id=?""",(assignment_id,)).fetchone()
    if not row or not row['chain_instance_id'] or not row['ordered_steps']: return True, None
    prior=db.execute("""SELECT COUNT(*) FROM assignments a JOIN quest_chain_steps s ON s.id=a.chain_step_id
                         JOIN chores c ON c.id=a.chore_id
                         WHERE a.chain_instance_id=? AND s.step_order < ?
                           AND c.active=1 AND a.status NOT IN ('completed','approved','cancelled')""",
                     (row['chain_instance_id'],row['step_order'])).fetchone()[0]
    return (prior==0, None if prior==0 else "Complete the earlier adventure steps first.")


def process_chain_completion(database, assignment_id:int):
    """Handle the process chain completion workflow."""
    row=database.execute("SELECT chain_instance_id FROM assignments WHERE id=?",(assignment_id,)).fetchone()
    if not row or not row['chain_instance_id']: return None
    instance_id=row['chain_instance_id']
    instance=database.execute("""SELECT qci.*,qc.name,qc.bonus_xp,qc.bonus_stars
                                 FROM quest_chain_instances qci JOIN quest_chains qc ON qc.id=qci.chain_id WHERE qci.id=?""",(instance_id,)).fetchone()
    if not instance or instance['status']=='completed': return None
    remaining=database.execute("SELECT COUNT(*) FROM assignments WHERE chain_instance_id=? AND status NOT IN ('approved','cancelled')",(instance_id,)).fetchone()[0]
    if remaining: return None
    now=datetime.now().isoformat()
    database.execute("UPDATE quest_chain_instances SET status='completed',completed_at=? WHERE id=?",(now,instance_id))
    user=database.execute("SELECT total_xp FROM users WHERE id=?",(instance['child_id'],)).fetchone()
    new_xp=int(user['total_xp'] or 0)+int(instance['bonus_xp'] or 0)
    database.execute("UPDATE users SET total_xp=?,current_level=? WHERE id=?",(new_xp,calculate_level(new_xp),instance['child_id']))
    if instance['bonus_stars']:
        award_stars(database,instance['child_id'],int(instance['bonus_stars']),f"Adventure completed: {instance['name']}",reference_type='QUEST_CHAIN',reference_id=instance_id,idempotency_key=f"chain:{instance_id}")
    database.execute(
        "INSERT INTO xp_history(child_id,xp,reason,family_id) VALUES(?,?,?,?)",
        (instance['child_id'], int(instance['bonus_xp'] or 0), f"Adventure completed: {instance['name']}", get_current_family_id()),
    )
    return dict(instance)


def child_chain_instances(child_id:int):
    """Return adventure instances with child-friendly progression states.

    Completing an ordered step immediately makes the next step available. Parent
    approval still controls XP, stars, and the final adventure completion bonus.
    """
    db=get_db(); rows=db.execute("""
      SELECT qci.*,qc.name,qc.description,qc.bonus_xp,qc.bonus_stars,qc.ordered_steps,
             SUM(CASE WHEN a.status!='cancelled' THEN 1 ELSE 0 END) total_steps,
             SUM(CASE WHEN a.status='approved' THEN 1 ELSE 0 END) approved_steps,
             SUM(CASE WHEN a.status IN ('completed','approved') THEN 1 ELSE 0 END) progressed_steps
      FROM quest_chain_instances qci JOIN quest_chains qc ON qc.id=qci.chain_id
      LEFT JOIN assignments a ON a.chain_instance_id=qci.id
      WHERE qci.child_id=? AND (qc.active=1 OR qci.status='completed') GROUP BY qci.id ORDER BY qci.status='active' DESC,qci.started_at DESC
    """,(child_id,)).fetchall()
    result=[]
    for r in rows:
        item=dict(r)
        total=item['total_steps'] or 1
        item['completed_steps']=item['approved_steps'] or 0
        item['percent']=round((item['progressed_steps'] or 0)/total*100)

        raw_steps=[dict(x) for x in db.execute("""SELECT a.id,a.status,c.title,s.step_order
          FROM assignments a
          JOIN chores c ON c.id=a.chore_id JOIN quest_chain_steps s ON s.id=a.chain_step_id
          WHERE a.chain_instance_id=? AND a.status!='cancelled' AND c.active=1 ORDER BY s.step_order""",(r['id'],)).fetchall()]

        prior_ready=True
        display_steps=[]
        for step in raw_steps:
            raw_status=step['status']
            if raw_status=='approved':
                display_status='approved'
            elif raw_status=='completed':
                display_status='waiting_for_approval'
            elif not item['ordered_steps'] or prior_ready:
                display_status='in_progress'
            else:
                display_status='not_started'

            step['display_status']=display_status
            display_steps.append(step)
            if item['ordered_steps'] and raw_status not in ('completed','approved'):
                prior_ready=False

        item['steps']=display_steps
        if item['status']=='completed':
            item['display_status']='approved'
        elif item['progressed_steps'] == item['total_steps'] and item['approved_steps'] < item['total_steps']:
            item['display_status']='waiting_for_approval'
        else:
            item['display_status']='in_progress'
        result.append(item)
    return result
