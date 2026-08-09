"""Content-driven character cosmetics for Family Quest Center."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from database import get_db
from services.tenant_context import get_current_family_id

CONTENT_FILE = Path(__file__).resolve().parent.parent / "content" / "cosmetics.json"
CATEGORIES = ("avatars", "frames", "themes")


def _active_pack_manifest_cosmetics() -> dict:
    """Return cosmetic definitions from active installed pack manifests.

    Character Workshop should reflect the current manifest for each installed,
    active pack rather than depending only on the cosmetic rows copied into the
    database when the pack was first installed. This lets pack updates add new
    avatar variants (for example skin-tone choices) without requiring a full
    reinstall or duplicating gameplay content.
    """
    result = {category: [] for category in CATEGORIES}
    database = get_db()
    family_id = get_current_family_id()

    # Older/fresh databases may not have pack tracking yet.
    tables = {
        row["name"]
        for row in database.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    if "family_content_packs" not in tables:
        return result

    active_pack_keys = [
        row["pack_key"]
        for row in database.execute(
            """SELECT pack_key
               FROM family_content_packs
               WHERE family_id=? AND status='active'""",
            (family_id,),
        ).fetchall()
    ]
    if not active_pack_keys:
        return result

    packs_root = Path(__file__).resolve().parent.parent / "content" / "packs"
    manifests_by_id = {}
    for manifest_path in packs_root.glob("*/pack.json"):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        pack_id = manifest.get("id")
        if pack_id:
            manifests_by_id[pack_id] = (manifest, manifest_path.parent.name)

    for pack_key in active_pack_keys:
        found = manifests_by_id.get(pack_key)
        if not found:
            continue
        manifest, folder_name = found
        for category in CATEGORIES:
            for item in manifest.get(category, []) or []:
                entry = dict(item)
                image = entry.get("image")
                if image and image.startswith("/parent/content-packs/assets/"):
                    parts = image.split("/")
                    # ['', 'parent', 'content-packs', 'assets', '<pack>', ...]
                    if len(parts) >= 6:
                        parts[4] = folder_name
                        entry["image"] = "/".join(parts)
                entry["pack_manifest"] = True
                result[category].append(entry)

    return result


@lru_cache(maxsize=1)
def load_cosmetics() -> dict:
    """Load cosmetic definitions from JSON once per process."""
    with CONTENT_FILE.open("r", encoding="utf-8") as file:
        data = json.load(file)
    for category in CATEGORIES:
        data.setdefault(category, [])
    return data


def ensure_family_cosmetics_table() -> None:
    """Handle the ensure family cosmetics table workflow."""
    database = get_db()
    database.executescript(
        """
        CREATE TABLE IF NOT EXISTS family_cosmetics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            family_id INTEGER NOT NULL,
            category TEXT NOT NULL CHECK(category IN ('avatars','frames','themes')),
            item_key TEXT NOT NULL,
            name TEXT NOT NULL,
            icon TEXT NOT NULL,
            image TEXT,
            class_name TEXT,
            unlock_type TEXT NOT NULL DEFAULT 'ALWAYS',
            unlock_value INTEGER NOT NULL DEFAULT 0,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(family_id, category, item_key)
        );
        CREATE INDEX IF NOT EXISTS idx_family_cosmetics_family
            ON family_cosmetics(family_id, category, active);
        """
    )
    columns = {
        row["name"]
        for row in database.execute(
            "PRAGMA table_info(family_cosmetics)"
        ).fetchall()
    }
    if "image" not in columns:
        database.execute("ALTER TABLE family_cosmetics ADD COLUMN image TEXT")
    database.commit()


def _family_cosmetics() -> dict:
    """Return valid family cosmetic rows while suppressing stale pack assets.

    Older databases can retain family_cosmetics rows after a development pack
    folder has been removed from the application. Those rows previously caused
    Character Workshop to render broken <img> URLs. If a cosmetic is tracked to
    a Content Pack, it is shown only when that pack is still installed as active,
    its current manifest exists on disk, and the cosmetic key still exists in
    that manifest. Non-pack family cosmetics continue to work normally.
    """
    ensure_family_cosmetics_table()
    family_id = get_current_family_id()
    database = get_db()

    tables = {
        row["name"]
        for row in database.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }

    has_tracking = {
        "content_pack_items",
        "family_content_packs",
    }.issubset(tables)

    if has_tracking:
        rows = database.execute(
            """SELECT fc.id,fc.category,fc.item_key,fc.name,fc.icon,fc.image,
                      fc.class_name,fc.unlock_type,fc.unlock_value,fc.active,
                      cpi.pack_key,
                      fcp.status AS pack_status
               FROM family_cosmetics fc
               LEFT JOIN content_pack_items cpi
                 ON cpi.family_id=fc.family_id
                AND cpi.item_type='cosmetic'
                AND cpi.item_id=fc.id
               LEFT JOIN family_content_packs fcp
                 ON fcp.family_id=fc.family_id
                AND fcp.pack_key=cpi.pack_key
               WHERE fc.family_id=?""",
            (family_id,),
        ).fetchall()
    else:
        rows = database.execute(
            """SELECT id,category,item_key,name,icon,image,class_name,
                      unlock_type,unlock_value,active,
                      NULL AS pack_key,NULL AS pack_status
               FROM family_cosmetics
               WHERE family_id=?""",
            (family_id,),
        ).fetchall()

    packs_root = Path(__file__).resolve().parent.parent / "content" / "packs"
    manifest_cosmetic_keys = {}

    if packs_root.is_dir():
        for manifest_path in packs_root.glob("*/pack.json"):
            try:
                manifest = json.loads(
                    manifest_path.read_text(encoding="utf-8")
                )
            except (OSError, json.JSONDecodeError):
                continue

            pack_id = manifest.get("id")
            if not pack_id:
                continue

            keys = set()
            for category in CATEGORIES:
                for item in manifest.get(category, []) or []:
                    item_key = item.get("key")
                    if item_key:
                        keys.add((category, item_key))

            manifest_cosmetic_keys[pack_id] = keys

    result = {category: [] for category in CATEGORIES}
    seen_ids = set()

    for row in rows:
        # LEFT JOIN can produce duplicate rows if historical tracking duplicates
        # exist. Emit each family cosmetic once.
        if row["id"] in seen_ids:
            continue

        pack_key = row["pack_key"]
        if pack_key:
            # A pack cosmetic is valid only while its pack is active, its
            # current manifest is physically available, and this exact
            # cosmetic key still exists in that current manifest.
            if row["pack_status"] != "active":
                continue

            current_keys = manifest_cosmetic_keys.get(pack_key)
            if current_keys is None:
                continue

            if (row["category"], row["item_key"]) not in current_keys:
                continue

        seen_ids.add(row["id"])
        result[row["category"]].append({
            "id": row["id"],
            "key": row["item_key"],
            "name": row["name"],
            "icon": row["icon"],
            "image": row["image"],
            "class_name": row["class_name"],
            "unlock": {
                "type": row["unlock_type"],
                "value": int(row["unlock_value"] or 0),
            },
            "active": bool(row["active"]),
            "family_cosmetic": True,
        })

    return result


def get_available_cosmetics() -> dict:
    """Retrieve available cosmetics from core, installed rows, and active manifests."""
    combined = {
        category: list(load_cosmetics().get(category, []))
        for category in CATEGORIES
    }
    family_items = _family_cosmetics()
    manifest_items = _active_pack_manifest_cosmetics()

    for category in CATEGORIES:
        # Priority order:
        # 1. Core definitions
        # 2. Existing family cosmetic rows
        # 3. Current manifest definitions for active installed packs
        #
        # The manifest wins for matching keys so updated image paths, new names,
        # and new tone variants appear immediately in Character Workshop.
        by_key = {item.get("key"): item for item in combined[category]}

        for item in family_items[category]:
            if item.get("active", True):
                by_key[item.get("key")] = item

        for item in manifest_items[category]:
            by_key[item.get("key")] = item

        combined[category] = list(by_key.values())

    return combined


def _achievement_count(database, child_id: int) -> int:
    """Handle the achievement count workflow."""
    row = database.execute(
        "SELECT COUNT(*) AS value FROM user_achievements WHERE user_id = ?",
        (child_id,),
    ).fetchone()
    return int(row["value"] or 0)


def get_unlock_context(child_id: int) -> dict:
    """Retrieve unlock context."""
    database = get_db()
    child = database.execute(
        "SELECT current_level FROM users WHERE id = ? AND role = 'child'",
        (child_id,),
    ).fetchone()
    if child is None:
        return {"LEVEL": 1, "ACHIEVEMENTS": 0}
    return {
        "LEVEL": int(child["current_level"] or 1),
        "ACHIEVEMENTS": _achievement_count(database, child_id),
    }


def is_unlocked(item: dict, context: dict) -> bool:
    """Determine whether is unlocked."""
    rule = item.get("unlock", {})
    rule_type = rule.get("type", "ALWAYS")
    required = int(rule.get("value", 0) or 0)
    if rule_type == "ALWAYS":
        return True
    return int(context.get(rule_type, 0)) >= required


def describe_unlock(item: dict) -> str:
    """Handle the describe unlock workflow."""
    rule = item.get("unlock", {})
    rule_type = rule.get("type", "ALWAYS")
    value = int(rule.get("value", 0) or 0)
    if rule_type == "ALWAYS":
        return "Available now"
    if rule_type == "LEVEL":
        return f"Reach Level {value}"
    if rule_type == "ACHIEVEMENTS":
        return f"Earn {value} achievements"
    return "Locked"


def get_cosmetic_options(child_id: int) -> dict:
    """Retrieve cosmetic options."""
    context = get_unlock_context(child_id)
    result = {}
    for category, items in get_available_cosmetics().items():
        result[category] = [
            {
                **item,
                "unlocked": is_unlocked(item, context),
                "unlock_text": describe_unlock(item),
            }
            for item in items
        ]
    return result


def get_item(category: str, key: str) -> dict | None:
    """Retrieve item."""
    for item in get_available_cosmetics().get(category, []):
        if item.get("key") == key:
            return item
    return None


def get_character_profile(child) -> dict:
    """Resolve saved cosmetic keys to safe display values."""
    defaults = {
        "avatar_key": "adventurer",
        "frame_key": "bronze",
        "theme_key": "quest",
    }
    profile = {}
    mapping = {
        "avatar": ("avatars", "avatar_key"),
        "frame": ("frames", "frame_key"),
        "theme": ("themes", "theme_key"),
    }
    for name, (category, field) in mapping.items():
        key = (
            child[field]
            if field in child.keys() and child[field]
            else defaults[field]
        )
        item = (
            get_item(category, key)
            or get_item(category, defaults[field])
        )
        profile[name] = item
    return profile


def save_character_choices(
    child_id: int,
    avatar_key: str,
    frame_key: str,
    theme_key: str,
) -> tuple[bool, str]:
    """Handle the save character choices workflow."""
    selections = {
        "avatars": avatar_key,
        "frames": frame_key,
        "themes": theme_key,
    }
    context = get_unlock_context(child_id)
    for category, key in selections.items():
        item = get_item(category, key)
        if item is None:
            return False, "One of the selected cosmetics does not exist."
        if not is_unlocked(item, context):
            return False, f"{item['name']} is still locked."

    database = get_db()
    database.execute(
        """
        UPDATE users
        SET avatar_key = ?, title_key = ?, frame_key = ?, theme_key = ?
        WHERE id = ? AND role = 'child'
        """,
        (avatar_key, avatar_key, frame_key, theme_key, child_id),
    )
    database.commit()
    return True, "Character updated successfully."
