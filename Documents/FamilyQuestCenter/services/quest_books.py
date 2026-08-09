"""Quest Books library, branching reader, and per-child progress helpers."""
from __future__ import annotations

import json
from pathlib import Path

from flask import current_app

from database import get_db
from models.progression import calculate_level
from services.content_packs import ensure_content_pack_tables, load_pack
from services.tenant_context import get_current_family_id


def ensure_quest_book_tables() -> None:
    """Create the per-child Quest Book progress table safely."""
    db = get_db()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS quest_book_progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            family_id INTEGER NOT NULL,
            child_id INTEGER NOT NULL,
            pack_key TEXT NOT NULL,
            book_key TEXT NOT NULL,
            current_node TEXT NOT NULL,
            steps_taken INTEGER NOT NULL DEFAULT 0,
            started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            completed_at TEXT,
            xp_awarded INTEGER NOT NULL DEFAULT 0,
            UNIQUE(family_id, child_id, pack_key, book_key),
            FOREIGN KEY(family_id) REFERENCES families(id),
            FOREIGN KEY(child_id) REFERENCES users(id)
        );
        CREATE INDEX IF NOT EXISTS idx_quest_book_progress_child
            ON quest_book_progress(family_id, child_id, updated_at);
        """
    )
    db.commit()


def _content_packs_root() -> Path:
    return Path(current_app.root_path) / "content" / "packs"


def _pack_folder(pack_key: str) -> Path:
    """Find the canonical folder for a manifest id."""
    for manifest_path in sorted(_content_packs_root().glob("*/pack.json")):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if manifest.get("id") == pack_key:
            return manifest_path.parent
    raise FileNotFoundError(f"Content Pack not found: {pack_key}")


def _validate_book_metadata(book: dict, pack_key: str) -> dict:
    required = ("id", "title", "file")
    missing = [field for field in required if not book.get(field)]
    if missing:
        raise ValueError(f"Invalid Quest Book in {pack_key}: missing {', '.join(missing)}")
    result = dict(book)
    result.setdefault("description", "Choose your path and see where the story leads.")
    result.setdefault("icon", "📖")
    result.setdefault("estimated_minutes", 10)
    result.setdefault("xp_reward", 0)
    result["xp_reward"] = max(0, int(result.get("xp_reward", 0)))
    return result


def _load_story(pack_key: str, book: dict) -> dict:
    pack_folder = _pack_folder(pack_key).resolve()
    story_path = (pack_folder / str(book["file"])).resolve()
    if pack_folder not in story_path.parents:
        raise ValueError("Quest Book file must stay inside its Content Pack folder.")
    try:
        story = json.loads(story_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Unable to load Quest Book: {book['title']}") from exc
    start_node = story.get("start_node", "start")
    nodes = story.get("nodes")
    if not isinstance(nodes, dict) or start_node not in nodes:
        raise ValueError(f"Quest Book {book['title']} has an invalid story structure.")
    for node_id, node in nodes.items():
        if not isinstance(node, dict) or not node.get("text"):
            raise ValueError(f"Quest Book {book['title']} has an invalid node: {node_id}")
        choices = node.get("choices", [])
        if not node.get("ending") and not choices:
            raise ValueError(f"Quest Book {book['title']} node {node_id} needs a choice or ending flag.")
        for choice in choices:
            next_node = choice.get("next") or choice.get("id")
            if not next_node or next_node not in nodes:
                raise ValueError(f"Quest Book {book['title']} has a broken choice from {node_id}.")
    story["start_node"] = start_node
    return story


def _active_installed_pack_keys() -> list[str]:
    ensure_content_pack_tables()
    rows = get_db().execute(
        """SELECT pack_key FROM family_content_packs
           WHERE family_id=? AND status='active' ORDER BY installed_at, id""",
        (get_current_family_id(),),
    ).fetchall()
    return [row["pack_key"] for row in rows]


def _child_row(child_id: int):
    return get_db().execute(
        """SELECT id,name,initial,total_xp,current_level FROM users
           WHERE id=? AND family_id=? AND role='child' AND active=1""",
        (int(child_id), get_current_family_id()),
    ).fetchone()


def list_available_books(child_id: int | None = None) -> list[dict]:
    """List books delivered by currently active family packs."""
    ensure_quest_book_tables()
    db = get_db()
    progress_by_key = {}
    if child_id is not None:
        if _child_row(child_id) is None:
            raise ValueError("Child profile not found.")
        progress_by_key = {
            (row["pack_key"], row["book_key"]): dict(row)
            for row in db.execute(
                """SELECT pack_key,book_key,current_node,steps_taken,started_at,updated_at,
                          completed_at,xp_awarded
                   FROM quest_book_progress
                   WHERE family_id=? AND child_id=?""",
                (get_current_family_id(), int(child_id)),
            ).fetchall()
        }

    books = []
    seen_ids = set()
    for pack_key in _active_installed_pack_keys():
        try:
            pack = load_pack(pack_key)
        except FileNotFoundError:
            continue
        for raw_book in pack.get("books", []):
            book = _validate_book_metadata(raw_book, pack_key)
            if book["id"] in seen_ids:
                raise ValueError(f"Duplicate Quest Book id detected: {book['id']}")
            seen_ids.add(book["id"])
            item = dict(book)
            item["pack_key"] = pack_key
            item["pack_name"] = pack["name"]
            item["progress"] = progress_by_key.get((pack_key, book["id"]))
            if item["progress"] and item["progress"].get("completed_at"):
                item["status"] = "completed"
                item["action_label"] = "Read Again"
            elif item["progress"]:
                item["status"] = "in_progress"
                item["action_label"] = "Continue Book"
            else:
                item["status"] = "not_started"
                item["action_label"] = "Start Book"
            books.append(item)
    return books


def get_available_book(book_key: str) -> dict:
    """Return one family-available book and its validated story."""
    for pack_key in _active_installed_pack_keys():
        try:
            pack = load_pack(pack_key)
        except FileNotFoundError:
            continue
        for raw_book in pack.get("books", []):
            book = _validate_book_metadata(raw_book, pack_key)
            if book["id"] != book_key:
                continue
            result = dict(book)
            result["pack_key"] = pack_key
            result["pack_name"] = pack["name"]
            result["story"] = _load_story(pack_key, result)
            return result
    raise FileNotFoundError("Quest Book is not available for this family.")


def get_reader_context(child_id: int, book_key: str) -> dict:
    """Start or continue a Quest Book for one child."""
    ensure_quest_book_tables()
    child = _child_row(child_id)
    if child is None:
        raise ValueError("Child profile not found.")
    book = get_available_book(book_key)
    db = get_db()
    progress = db.execute(
        """SELECT * FROM quest_book_progress
           WHERE family_id=? AND child_id=? AND pack_key=? AND book_key=?""",
        (get_current_family_id(), int(child_id), book["pack_key"], book_key),
    ).fetchone()
    if progress is None:
        db.execute(
            """INSERT INTO quest_book_progress(
                   family_id,child_id,pack_key,book_key,current_node,steps_taken
               ) VALUES(?,?,?,?,?,0)""",
            (get_current_family_id(), int(child_id), book["pack_key"], book_key, book["story"]["start_node"]),
        )
        db.commit()
        progress = db.execute(
            """SELECT * FROM quest_book_progress
               WHERE family_id=? AND child_id=? AND pack_key=? AND book_key=?""",
            (get_current_family_id(), int(child_id), book["pack_key"], book_key),
        ).fetchone()

    node = book["story"]["nodes"].get(progress["current_node"])
    if node is None:
        raise ValueError("Saved Quest Book progress points to a missing story section.")
    return {
        "child": dict(child),
        "book": book,
        "progress": dict(progress),
        "node": node,
        "node_id": progress["current_node"],
    }


def choose_path(child_id: int, book_key: str, next_node: str) -> dict:
    """Validate one branch choice, save progress, and award completion XP once."""
    context = get_reader_context(child_id, book_key)
    book = context["book"]
    current_node = context["node"]
    valid_next = {
        (choice.get("next") or choice.get("id"))
        for choice in current_node.get("choices", [])
    }
    if next_node not in valid_next:
        raise ValueError("That story choice is not available from this page.")

    target = book["story"]["nodes"].get(next_node)
    if target is None:
        raise ValueError("That story path could not be found.")

    db = get_db()
    family_id = get_current_family_id()
    progress = context["progress"]
    completed_now = bool(target.get("ending"))
    xp_awarded_now = 0

    try:
        if completed_now:
            db.execute(
                """UPDATE quest_book_progress
                   SET current_node=?,steps_taken=steps_taken+1,
                       updated_at=CURRENT_TIMESTAMP,completed_at=CURRENT_TIMESTAMP
                   WHERE id=? AND family_id=? AND child_id=?""",
                (next_node, progress["id"], family_id, int(child_id)),
            )
            if not int(progress.get("xp_awarded", 0)) and int(book.get("xp_reward", 0)) > 0:
                xp_awarded_now = int(book["xp_reward"])
                row = db.execute(
                    "SELECT total_xp FROM users WHERE id=? AND family_id=? AND role='child'",
                    (int(child_id), family_id),
                ).fetchone()
                if row is None:
                    raise ValueError("Child profile not found.")
                new_total_xp = int(row["total_xp"] or 0) + xp_awarded_now
                db.execute(
                    "UPDATE users SET total_xp=?,current_level=? WHERE id=? AND family_id=?",
                    (new_total_xp, calculate_level(new_total_xp), int(child_id), family_id),
                )
                db.execute(
                    "UPDATE quest_book_progress SET xp_awarded=1 WHERE id=? AND family_id=?",
                    (progress["id"], family_id),
                )
        else:
            db.execute(
                """UPDATE quest_book_progress
                   SET current_node=?,steps_taken=steps_taken+1,updated_at=CURRENT_TIMESTAMP
                   WHERE id=? AND family_id=? AND child_id=?""",
                (next_node, progress["id"], family_id, int(child_id)),
            )
        db.commit()
    except Exception:
        db.rollback()
        raise

    return {
        "completed": completed_now,
        "xp_awarded": xp_awarded_now,
        "next_node": next_node,
    }


def restart_book(child_id: int, book_key: str) -> None:
    """Restart a story without allowing repeat XP awards."""
    context = get_reader_context(child_id, book_key)
    db = get_db()
    db.execute(
        """UPDATE quest_book_progress
           SET current_node=?,steps_taken=0,updated_at=CURRENT_TIMESTAMP,completed_at=NULL
           WHERE id=? AND family_id=? AND child_id=?""",
        (
            context["book"]["story"]["start_node"],
            context["progress"]["id"],
            get_current_family_id(),
            int(child_id),
        ),
    )
    db.commit()
