"""First-time family setup and child Explorer Training state."""
from __future__ import annotations

from contextlib import closing

import sqlite3
from pathlib import Path

from database import get_db
from services.tenant_context import get_current_family_id


def ensure_onboarding_schema(database_path: Path) -> None:
    """Handle the ensure onboarding schema workflow."""
    with closing(sqlite3.connect(database_path)) as db, db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS family_onboarding (
                family_id INTEGER PRIMARY KEY,
                approvals_acknowledged INTEGER NOT NULL DEFAULT 0,
                setup_completed INTEGER NOT NULL DEFAULT 0,
                completed_at TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (family_id) REFERENCES families(id)
            );

            CREATE TABLE IF NOT EXISTS child_training (
                child_id INTEGER PRIMARY KEY,
                training_completed INTEGER NOT NULL DEFAULT 0,
                completed_at TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (child_id) REFERENCES users(id)
            );
            """
        )
        db.commit()


def _ensure_family_row(family_id: int) -> None:
    """Handle the ensure family row workflow."""
    db = get_db()
    db.execute(
        "INSERT OR IGNORE INTO family_onboarding(family_id) VALUES(?)",
        (family_id,),
    )
    db.commit()


def get_setup_status() -> dict:
    """Retrieve setup status."""
    family_id = get_current_family_id()
    _ensure_family_row(family_id)
    db = get_db()
    state = db.execute(
        "SELECT approvals_acknowledged,setup_completed FROM family_onboarding WHERE family_id=?",
        (family_id,),
    ).fetchone()

    child_count = db.execute(
        "SELECT COUNT(*) FROM users WHERE family_id=? AND role='child' AND active=1",
        (family_id,),
    ).fetchone()[0]

    # A parent's first mission is considered assigned as soon as either a
    # one-time assignment exists or an active recurring Mission Builder
    # schedule has been created for the family.
    assignment_count = db.execute(
        "SELECT COUNT(*) FROM assignments WHERE family_id=?",
        (family_id,),
    ).fetchone()[0]
    schedule_count = db.execute(
        "SELECT COUNT(*) FROM quest_schedules WHERE family_id=? AND active=1",
        (family_id,),
    ).fetchone()[0]

    # Adventure tables are created lazily by the Growth System. A family may
    # reach onboarding before opening the Adventure Library, so treat a
    # not-yet-created table as zero assigned Adventures instead of raising an
    # OperationalError.
    adventure_table_exists = db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='adventure_instances_v2'"
    ).fetchone()
    adventure_count = 0
    if adventure_table_exists:
        adventure_count = db.execute(
            "SELECT COUNT(*) FROM adventure_instances_v2 WHERE family_id=?",
            (family_id,),
        ).fetchone()[0]

    steps = {
        "children": child_count > 0,
        "missions": (assignment_count + schedule_count) > 0,
        "adventures": adventure_count > 0,
    }
    completed_count = sum(1 for value in steps.values() if value)
    return {
        "family_id": family_id,
        "steps": steps,
        "completed_count": completed_count,
        "total_count": len(steps),
        "percent": round((completed_count / len(steps)) * 100),
        "ready": all(steps.values()),
        "approvals_acknowledged": bool(state["approvals_acknowledged"]),
        "setup_completed": bool(state["setup_completed"]),
    }


def acknowledge_approvals() -> None:
    """Handle the acknowledge approvals workflow."""
    family_id = get_current_family_id()
    _ensure_family_row(family_id)
    db = get_db()
    db.execute(
        "UPDATE family_onboarding SET approvals_acknowledged=1,updated_at=CURRENT_TIMESTAMP WHERE family_id=?",
        (family_id,),
    )
    db.commit()


def complete_family_setup() -> None:
    """Handle the complete family setup workflow."""
    family_id = get_current_family_id()
    _ensure_family_row(family_id)
    db = get_db()
    db.execute(
        """UPDATE family_onboarding
           SET setup_completed=1,completed_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP
           WHERE family_id=?""",
        (family_id,),
    )
    db.commit()


def family_setup_complete() -> bool:
    """Handle the family setup complete workflow."""
    family_id = get_current_family_id()
    _ensure_family_row(family_id)
    row = get_db().execute(
        "SELECT setup_completed FROM family_onboarding WHERE family_id=?",
        (family_id,),
    ).fetchone()
    return bool(row and row["setup_completed"])


def child_training_complete(child_id: int) -> bool:
    """Handle the child training complete workflow."""
    db = get_db()
    db.execute("INSERT OR IGNORE INTO child_training(child_id) VALUES(?)", (child_id,))
    db.commit()
    row = db.execute(
        "SELECT training_completed FROM child_training WHERE child_id=?",
        (child_id,),
    ).fetchone()
    return bool(row and row["training_completed"])


def complete_child_training(child_id: int) -> None:
    """Handle the complete child training workflow."""
    db = get_db()
    db.execute("INSERT OR IGNORE INTO child_training(child_id) VALUES(?)", (child_id,))
    db.execute(
        """UPDATE child_training SET training_completed=1,completed_at=CURRENT_TIMESTAMP,
           updated_at=CURRENT_TIMESTAMP WHERE child_id=?""",
        (child_id,),
    )
    db.commit()
