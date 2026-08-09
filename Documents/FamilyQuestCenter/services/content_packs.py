"""Content Pack discovery, installation, archiving, and family ownership tracking."""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from flask import current_app

from database import get_db
from services.tenant_context import get_current_family_id
from models.journeys import create_adventure_with_chapters, ensure_journey_tables
from models.achievements import ensure_family_achievement_tables
from models.cosmetics import ensure_family_cosmetics_table


_ITEM_TABLES = {
    "quest": ("chores", "active"),
    "adventure": ("adventures_v2", "active"),
    "challenge": ("family_challenges", "active"),
    "reward": ("rewards", "active"),
    "reward_category": ("reward_categories", "active"),
    "cosmetic": ("family_cosmetics", "active"),
}


def ensure_content_pack_tables() -> None:
    """Create or upgrade Content Pack tracking tables safely."""
    db = get_db()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS content_packs (
            pack_key TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            version TEXT NOT NULL,
            category TEXT NOT NULL,
            description TEXT,
            icon TEXT NOT NULL DEFAULT '📦',
            pack_type TEXT NOT NULL DEFAULT 'expansion',
            author TEXT NOT NULL DEFAULT 'Family Quest Center',
            archive_allowed INTEGER NOT NULL DEFAULT 1,
            price_type TEXT NOT NULL DEFAULT 'free',
            price_cents INTEGER NOT NULL DEFAULT 0,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS family_content_packs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            family_id INTEGER NOT NULL,
            pack_key TEXT NOT NULL,
            installed_version TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','archived')),
            installed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(family_id, pack_key),
            FOREIGN KEY(family_id) REFERENCES families(id),
            FOREIGN KEY(pack_key) REFERENCES content_packs(pack_key)
        );
        CREATE TABLE IF NOT EXISTS content_pack_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            family_id INTEGER NOT NULL,
            pack_key TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','denied')),
            requested_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            resolved_at TEXT,
            UNIQUE(family_id, pack_key),
            FOREIGN KEY(family_id) REFERENCES families(id),
            FOREIGN KEY(pack_key) REFERENCES content_packs(pack_key)
        );
        CREATE TABLE IF NOT EXISTS content_pack_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            family_id INTEGER NOT NULL,
            pack_key TEXT NOT NULL,
            item_type TEXT NOT NULL,
            item_id INTEGER NOT NULL,
            item_archived INTEGER NOT NULL DEFAULT 0,
            pack_archived INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(family_id, pack_key, item_type, item_id)
        );
        CREATE INDEX IF NOT EXISTS idx_family_content_packs_family ON family_content_packs(family_id,status);
        CREATE INDEX IF NOT EXISTS idx_content_pack_requests_family ON content_pack_requests(family_id,status);
        CREATE INDEX IF NOT EXISTS idx_content_pack_items_family ON content_pack_items(family_id,pack_key,item_type);
        """
    )
    # Pack requests were originally child-specific. Migrate older databases to
    # one request per family/pack while preserving the newest request state.
    request_columns = {row["name"]: row for row in db.execute("PRAGMA table_info(content_pack_requests)").fetchall()}
    request_sql_row = db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='content_pack_requests'").fetchone()
    request_sql = (request_sql_row["sql"] if request_sql_row else "") or ""
    if "child_id" in request_columns or "UNIQUE(family_id, child_id, pack_key)" in request_sql:
        old_rows = db.execute(
            "SELECT family_id,pack_key,status,requested_at,resolved_at FROM content_pack_requests ORDER BY id DESC"
        ).fetchall()
        db.execute("ALTER TABLE content_pack_requests RENAME TO content_pack_requests_child_legacy")
        db.execute(
            """CREATE TABLE content_pack_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                family_id INTEGER NOT NULL,
                pack_key TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','denied')),
                requested_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                resolved_at TEXT,
                UNIQUE(family_id, pack_key),
                FOREIGN KEY(family_id) REFERENCES families(id),
                FOREIGN KEY(pack_key) REFERENCES content_packs(pack_key)
            )"""
        )
        seen = set()
        for row in old_rows:
            key = (row["family_id"], row["pack_key"])
            if key in seen:
                continue
            seen.add(key)
            db.execute(
                "INSERT INTO content_pack_requests(family_id,pack_key,status,requested_at,resolved_at) VALUES(?,?,?,?,?)",
                (row["family_id"], row["pack_key"], row["status"], row["requested_at"], row["resolved_at"]),
            )
        db.execute("DROP TABLE content_pack_requests_child_legacy")
        db.execute("CREATE INDEX IF NOT EXISTS idx_content_pack_requests_family ON content_pack_requests(family_id,status)")

    item_columns = {row["name"] for row in db.execute("PRAGMA table_info(content_pack_items)").fetchall()}
    if "pack_archived" not in item_columns:
        db.execute("ALTER TABLE content_pack_items ADD COLUMN pack_archived INTEGER NOT NULL DEFAULT 0")
    pack_columns = {row["name"] for row in db.execute("PRAGMA table_info(content_packs)").fetchall()}
    for column, definition in {
        "pack_type": "TEXT NOT NULL DEFAULT 'expansion'",
        "author": "TEXT NOT NULL DEFAULT 'Family Quest Center'",
        "archive_allowed": "INTEGER NOT NULL DEFAULT 1",
        "price_type": "TEXT NOT NULL DEFAULT 'free'",
        "price_cents": "INTEGER NOT NULL DEFAULT 0",
    }.items():
        if column not in pack_columns:
            db.execute(f"ALTER TABLE content_packs ADD COLUMN {column} {definition}")
    db.commit()


def _content_root() -> Path:
    return Path(current_app.root_path) / "content"


def _manifest_paths() -> list[Path]:
    """Return bundled Content Pack manifests from the canonical packs folder."""
    return sorted((_content_root() / "packs").glob("*/pack.json"))


def _validate_pack(pack: dict, source: Path | None = None) -> dict:
    required = ("id", "name", "version", "category", "description")
    missing = [field for field in required if not pack.get(field)]
    if missing:
        location = f" in {source}" if source else ""
        raise ValueError(f"Invalid Content Pack{location}: missing {', '.join(missing)}")
    pack.setdefault("pack_type", "expansion")
    pack.setdefault("author", "Family Quest Center")
    pack.setdefault("discoverable", True)
    pack.setdefault("archive_allowed", pack["pack_type"] != "core")
    pack.setdefault("price_type", "free")
    pack.setdefault("price_cents", 0)
    if pack["price_type"] not in {"free", "paid"}:
        raise ValueError("Content Pack price_type must be 'free' or 'paid'.")
    pack["price_cents"] = max(0, int(pack.get("price_cents", 0)))
    return pack


def load_pack(pack_key: str) -> dict:
    """Load a pack by manifest id so core packs need not live under /packs."""
    for path in _manifest_paths():
        data = _validate_pack(json.loads(path.read_text(encoding="utf-8")), path)
        if data["id"] == pack_key:
            return data
    raise FileNotFoundError(f"Content Pack not found: {pack_key}")


def discover_packs() -> list[dict]:
    """Handle the discover packs workflow."""
    ensure_content_pack_tables()
    db = get_db()
    results = []
    for path in _manifest_paths():
        data = _validate_pack(json.loads(path.read_text(encoding="utf-8")), path)
        if not data.get("discoverable", True):
            continue
        results.append(data)
        db.execute(
            """INSERT INTO content_packs(pack_key,name,version,category,description,icon,pack_type,author,archive_allowed,price_type,price_cents)
               VALUES(?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(pack_key) DO UPDATE SET name=excluded.name,version=excluded.version,
                 category=excluded.category,description=excluded.description,icon=excluded.icon,
                 pack_type=excluded.pack_type,author=excluded.author,archive_allowed=excluded.archive_allowed,
                 price_type=excluded.price_type,price_cents=excluded.price_cents""",
            (data["id"], data["name"], data["version"], data.get("category", "general"),
             data.get("description"), data.get("icon", "📦"), data.get("pack_type", "expansion"),
             data.get("author", "Family Quest Center"), int(bool(data.get("archive_allowed", True))),
             data.get("price_type", "free"), int(data.get("price_cents", 0))),
        )
    db.commit()
    family_id = get_current_family_id()
    installed = {
        row["pack_key"]: dict(row)
        for row in db.execute(
            "SELECT pack_key,installed_version,status,installed_at,updated_at FROM family_content_packs WHERE family_id=?",
            (family_id,),
        ).fetchall()
    }
    request_rows = {
        row["pack_key"]: dict(row)
        for row in db.execute(
            "SELECT id,pack_key,status,requested_at,resolved_at FROM content_pack_requests WHERE family_id=? AND status='pending'",
            (family_id,),
        ).fetchall()
    }
    for item in results:
        item["installation"] = installed.get(item["id"])
        item["pending_request"] = request_rows.get(item["id"])
        item["price_label"] = "FREE" if item.get("price_type", "free") == "free" else f"${int(item.get('price_cents', 0)) / 100:.2f}"
        item["counts"] = {key: len(item.get(key, [])) for key in ("quests", "adventures", "challenges", "rewards", "achievements", "books", "avatars", "frames", "themes")}
        if not item["installation"]:
            item["manager_status"] = "available"
        elif item["installation"]["status"] == "archived":
            item["manager_status"] = "archived"
        elif str(item["installation"]["installed_version"]) != str(item["version"]):
            item["manager_status"] = "update_available"
        elif item.get("pack_type") == "core":
            item["manager_status"] = "built_in"
        else:
            item["manager_status"] = "installed"
        if item["installation"]:
            rows = db.execute(
                """SELECT item_type, COUNT(*) total,
                          SUM(CASE WHEN pack_archived=1 THEN 1 ELSE 0 END) pack_archived_count
                   FROM content_pack_items
                   WHERE family_id=? AND pack_key=? GROUP BY item_type""",
                (family_id, item["id"]),
            ).fetchall()
            item["installed_counts"] = {row["item_type"]: row["total"] for row in rows}
    return results


def _track(pack_key: str, item_type: str, item_id: int) -> None:
    """Handle the track workflow."""
    get_db().execute(
        "INSERT OR IGNORE INTO content_pack_items(family_id,pack_key,item_type,item_id) VALUES(?,?,?,?)",
        (get_current_family_id(), pack_key, item_type, item_id),
    )


def _register_pack_manifest(pack: dict) -> None:
    """Ensure the pack catalog row exists before family installation.

    Family installation rows reference ``content_packs(pack_key)``. Earlier
    versions relied on the Pack Manager discovery page to populate that
    catalog first. Account onboarding can install the starter pack before the
    Pack Manager has ever been opened, so the manifest must be registered as
    part of the installation transaction itself.
    """
    get_db().execute(
        """INSERT INTO content_packs(
               pack_key,name,version,category,description,icon,pack_type,author,archive_allowed,price_type,price_cents
           ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(pack_key) DO UPDATE SET
             name=excluded.name,
             version=excluded.version,
             category=excluded.category,
             description=excluded.description,
             icon=excluded.icon,
             pack_type=excluded.pack_type,
             author=excluded.author,
             archive_allowed=excluded.archive_allowed,
             price_type=excluded.price_type,
             price_cents=excluded.price_cents,
             active=1""",
        (
            pack["id"],
            pack["name"],
            str(pack["version"]),
            pack.get("category", "general"),
            pack.get("description"),
            pack.get("icon", "📦"),
            pack.get("pack_type", "expansion"),
            pack.get("author", "Family Quest Center"),
            int(bool(pack.get("archive_allowed", True))),
            pack.get("price_type", "free"),
            int(pack.get("price_cents", 0)),
        ),
    )


def install_pack(pack_key: str) -> dict[str, int]:
    """Install one Content Pack for the active family.

    The operation is self-contained and no longer depends on the family
    visiting the Pack Manager before onboarding.
    """
    ensure_content_pack_tables()
    pack = load_pack(pack_key)
    db = get_db()
    family_id = get_current_family_id()
    _register_pack_manifest(pack)
    if db.execute("SELECT 1 FROM family_content_packs WHERE family_id=? AND pack_key=?", (family_id, pack_key)).fetchone():
        raise ValueError("This Content Pack is already installed for your family.")
    counts = {"quests": 0, "adventures": 0, "challenges": 0, "reward_categories": 0, "rewards": 0, "achievements": 0, "books": len(pack.get("books", [])), "avatars": 0, "frames": 0, "themes": 0}
    try:
        reward_category_ids = {}
        for category in pack.get("reward_categories", []):
            existing = db.execute(
                "SELECT id FROM reward_categories WHERE family_id=? AND name=?",
                (family_id, category["name"]),
            ).fetchone()
            if existing:
                category_id = existing["id"]
            else:
                cur = db.execute(
                    """INSERT INTO reward_categories(name,icon,display_order,active,family_id)
                       VALUES(?,?,?,?,?)""",
                    (category["name"], category.get("icon", "🎁"), int(category.get("display_order", 0)), 1, family_id),
                )
                category_id = cur.lastrowid
            reward_category_ids[category.get("key", category["name"])] = category_id
            _track(pack_key, "reward_category", category_id)
            counts["reward_categories"] += 1

        for quest in pack.get("quests", []):
            title = quest["name"] + (f" ({quest['subtitle']})" if quest.get("subtitle") else "")
            cur = db.execute(
                """INSERT INTO chores(title,description,difficulty,stars,approval_required,active,family_id)
                   VALUES(?,?,?,?,1,1,?)""",
                (title, quest.get("description", ""), int(quest.get("difficulty", 1)), int(quest.get("stars", 10)), family_id),
            )
            _track(pack_key, "quest", cur.lastrowid)
            counts["quests"] += 1
        for adventure in pack.get("adventures", []):
            adventure_id = create_adventure_with_chapters(
                adventure["name"], adventure.get("description", ""), int(adventure.get("bonus_xp", 100)), adventure.get("chapters", [])
            )
            _track(pack_key, "adventure", adventure_id)
            counts["adventures"] += 1
        today = date.today()
        for challenge in pack.get("challenges", []):
            end = today + timedelta(days=max(1, int(challenge.get("duration_days", 7))) - 1)
            cur = db.execute(
                """INSERT INTO family_challenges(name,description,goal_type,target_value,start_date,end_date,reward_text,active,family_id)
                   VALUES(?,?,?,?,?,?,?,?,?)""",
                (
                    challenge["name"], challenge.get("description", ""), challenge.get("goal_type", "quests"),
                    int(challenge.get("target_value", 1)), today.isoformat(), end.isoformat(), challenge.get("reward_text", ""), 1, family_id,
                ),
            )
            _track(pack_key, "challenge", cur.lastrowid)
            counts["challenges"] += 1
        for reward in pack.get("rewards", []):
            category_id = reward_category_ids.get(reward.get("category_key"))
            cur = db.execute(
                """INSERT INTO rewards(category_id,name,description,icon,cost,quantity,requires_approval,active,family_id)
                   VALUES(?,?,?,?,?,NULL,1,1,?)""",
                (category_id, reward["name"], reward.get("description", ""), reward.get("icon", "🎁"), int(reward.get("cost", 100)), family_id),
            )
            _track(pack_key, "reward", cur.lastrowid)
            counts["rewards"] += 1
        ensure_family_achievement_tables()
        for achievement in pack.get("achievements", []):
            existing = db.execute(
                "SELECT id FROM achievements WHERE name=? AND is_system=0",
                (achievement["name"],),
            ).fetchone()
            if existing:
                achievement_id = existing["id"]
                db.execute(
                    "UPDATE achievements SET active=1, is_system=0 WHERE id=?",
                    (achievement_id,),
                )
            else:
                achievement_id = db.execute(
                    """INSERT INTO achievements(name,description,icon,category,requirement_type,
                           requirement_value,xp_reward,star_reward,hidden,active,is_system)
                       VALUES(?,?,?,?,?,?,?,?,?,1,0)""",
                    (achievement["name"], achievement.get("description", ""), achievement.get("icon", "🏆"),
                     achievement.get("category", "Pack Achievements"), achievement.get("requirement_type", "QUESTS_COMPLETED"),
                     int(achievement.get("requirement_value", 1)), int(achievement.get("xp_reward", 0)),
                     int(achievement.get("star_reward", 0)), int(bool(achievement.get("hidden", False)))),
                ).lastrowid
            db.execute(
                "INSERT INTO family_achievements(family_id,achievement_id,active) VALUES(?,?,1) ON CONFLICT(family_id,achievement_id) DO UPDATE SET active=excluded.active",
                (family_id, achievement_id),
            )
            _track(pack_key, "achievement", achievement_id)
            counts["achievements"] += 1

        ensure_family_cosmetics_table()
        for category in ("avatars", "frames", "themes"):
            for cosmetic in pack.get(category, []):
                cur = db.execute(
                    """INSERT INTO family_cosmetics(family_id,category,item_key,name,icon,image,class_name,unlock_type,unlock_value,active)
                       VALUES(?,?,?,?,?,?,?,?,?,1)
                       ON CONFLICT(family_id,category,item_key) DO UPDATE SET
                         name=excluded.name,icon=excluded.icon,image=excluded.image,class_name=excluded.class_name,
                         unlock_type=excluded.unlock_type,unlock_value=excluded.unlock_value,active=1""",
                    (family_id, category, cosmetic["key"], cosmetic["name"], cosmetic.get("icon", "⭐"),
                     cosmetic.get("image"), cosmetic.get("class_name"), cosmetic.get("unlock", {}).get("type", "ALWAYS"),
                     int(cosmetic.get("unlock", {}).get("value", 0))),
                )
                cosmetic_id = db.execute(
                    "SELECT id FROM family_cosmetics WHERE family_id=? AND category=? AND item_key=?",
                    (family_id, category, cosmetic["key"]),
                ).fetchone()["id"]
                _track(pack_key, "cosmetic", cosmetic_id)
                counts[category] += 1
        db.execute(
            "INSERT INTO family_content_packs(family_id,pack_key,installed_version,status) VALUES(?,?,?,'active')",
            (family_id, pack_key, pack["version"]),
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return counts


def _get_item_active(item_type: str, item_id: int, family_id: int) -> bool | None:
    """Return current archive state for a family-owned pack item."""
    if item_type == "achievement":
        ensure_family_achievement_tables()
        row = get_db().execute(
            "SELECT active FROM family_achievements WHERE family_id=? AND achievement_id=?",
            (family_id, item_id),
        ).fetchone()
        return None if row is None else bool(row["active"])
    if item_type not in _ITEM_TABLES:
        return None
    if item_type == "adventure":
        ensure_journey_tables()
    table, active_column = _ITEM_TABLES[item_type]
    row = get_db().execute(
        f"SELECT {active_column} AS active FROM {table} WHERE id=? AND family_id=?",
        (item_id, family_id),
    ).fetchone()
    return None if row is None else bool(row["active"])


def _set_item_active(item_type: str, item_id: int, family_id: int, active: bool) -> int:
    """Set a family-owned pack item active/archived and return affected rows."""
    if item_type == "achievement":
        ensure_family_achievement_tables()
        cur = get_db().execute(
            "UPDATE family_achievements SET active=? WHERE family_id=? AND achievement_id=?",
            (1 if active else 0, family_id, item_id),
        )
        return cur.rowcount
    if item_type not in _ITEM_TABLES:
        return 0
    if item_type == "adventure":
        ensure_journey_tables()
    table, active_column = _ITEM_TABLES[item_type]
    cur = get_db().execute(
        f"UPDATE {table} SET {active_column}=? WHERE id=? AND family_id=?",
        (1 if active else 0, item_id, family_id),
    )
    return cur.rowcount



def update_pack_cosmetics(pack_key: str) -> dict[str, int]:
    """Update an installed pack's cosmetic definitions without duplicating content.

    This update path is intentionally conservative: quests, adventures, rewards,
    achievements, challenges, and books are not reinserted. Image/avatar/frame/theme
    definitions are synchronized from the current manifest, removed cosmetic
    definitions from the same pack are deactivated, and the family's installed
    version is advanced to the manifest version.
    """
    ensure_content_pack_tables()
    pack = load_pack(pack_key)
    db = get_db()
    family_id = get_current_family_id()

    installation = db.execute(
        "SELECT status FROM family_content_packs WHERE family_id=? AND pack_key=?",
        (family_id, pack_key),
    ).fetchone()
    if not installation:
        raise ValueError("This Content Pack is not installed for your family.")
    if installation["status"] != "active":
        raise ValueError("Restore this Content Pack before updating it.")

    _register_pack_manifest(pack)
    ensure_family_cosmetics_table()
    counts = {"reward_categories": 0, "challenges_removed": 0, "avatars": 0, "frames": 0, "themes": 0}

    try:
        # Starter/default categories are pack seed data. Once installed, tracked
        # rows belong to the family and are not renamed or overwritten by updates.
        tracked_category_ids = {
            row["item_id"]
            for row in db.execute(
                "SELECT item_id FROM content_pack_items WHERE family_id=? AND pack_key=? AND item_type='reward_category'",
                (family_id, pack_key),
            ).fetchall()
        }
        # Seed any starter-pack reward categories that are still missing.
        # Existing family-owned categories are preserved exactly as the parent
        # has customized them; we only create/track missing seed categories.
        for category in pack.get("reward_categories", []):
            existing = db.execute(
                "SELECT id FROM reward_categories WHERE family_id=? AND name=?",
                (family_id, category["name"]),
            ).fetchone()
            if existing:
                category_id = existing["id"]
            else:
                cur = db.execute(
                    """INSERT INTO reward_categories(name,icon,display_order,active,family_id)
                       VALUES(?,?,?,?,?)""",
                    (category["name"], category.get("icon", "🎁"),
                     int(category.get("display_order", 0)), 1, family_id),
                )
                category_id = cur.lastrowid
                counts["reward_categories"] += 1

            if category_id not in tracked_category_ids:
                _track(pack_key, "reward_category", category_id)
                tracked_category_ids.add(category_id)

        # If a pack update intentionally removes every challenge, retire any
        # challenge rows previously installed by that pack for this family.
        if not pack.get("challenges", []):
            tracked_challenges = db.execute(
                """SELECT cpi.id AS tracking_id,cpi.item_id
                   FROM content_pack_items cpi
                   WHERE cpi.family_id=? AND cpi.pack_key=? AND cpi.item_type='challenge'""",
                (family_id, pack_key),
            ).fetchall()
            for row in tracked_challenges:
                changed = db.execute(
                    "UPDATE family_challenges SET active=0 WHERE id=? AND family_id=? AND active=1",
                    (row["item_id"], family_id),
                ).rowcount
                if changed:
                    counts["challenges_removed"] += 1
                db.execute(
                    "UPDATE content_pack_items SET item_archived=1 WHERE id=?",
                    (row["tracking_id"],),
                )

        manifest_keys = set()
        for category in ("avatars", "frames", "themes"):
            for cosmetic in pack.get(category, []):
                manifest_keys.add((category, cosmetic["key"]))
                db.execute(
                    """INSERT INTO family_cosmetics(
                           family_id,category,item_key,name,icon,image,class_name,
                           unlock_type,unlock_value,active
                       ) VALUES(?,?,?,?,?,?,?,?,?,1)
                       ON CONFLICT(family_id,category,item_key) DO UPDATE SET
                         name=excluded.name,
                         icon=excluded.icon,
                         image=excluded.image,
                         class_name=excluded.class_name,
                         unlock_type=excluded.unlock_type,
                         unlock_value=excluded.unlock_value,
                         active=1""",
                    (
                        family_id,
                        category,
                        cosmetic["key"],
                        cosmetic["name"],
                        cosmetic.get("icon", "⭐"),
                        cosmetic.get("image"),
                        cosmetic.get("class_name"),
                        cosmetic.get("unlock", {}).get("type", "ALWAYS"),
                        int(cosmetic.get("unlock", {}).get("value", 0)),
                    ),
                )
                cosmetic_id = db.execute(
                    "SELECT id FROM family_cosmetics WHERE family_id=? AND category=? AND item_key=?",
                    (family_id, category, cosmetic["key"]),
                ).fetchone()["id"]
                _track(pack_key, "cosmetic", cosmetic_id)
                counts[category] += 1

        # Cosmetic rows previously installed by this pack but removed from the
        # current manifest should no longer appear in Character Workshop.
        tracked = db.execute(
            """SELECT cpi.id AS tracking_id, fc.id AS cosmetic_id,
                      fc.category, fc.item_key
               FROM content_pack_items cpi
               JOIN family_cosmetics fc
                 ON cpi.item_type='cosmetic'
                AND cpi.item_id=fc.id
                AND cpi.family_id=fc.family_id
               WHERE cpi.family_id=? AND cpi.pack_key=?""",
            (family_id, pack_key),
        ).fetchall()
        for row in tracked:
            if (row["category"], row["item_key"]) not in manifest_keys:
                db.execute(
                    "UPDATE family_cosmetics SET active=0 WHERE id=? AND family_id=?",
                    (row["cosmetic_id"], family_id),
                )

        db.execute(
            """UPDATE family_content_packs
               SET installed_version=?, updated_at=CURRENT_TIMESTAMP
               WHERE family_id=? AND pack_key=?""",
            (str(pack["version"]), family_id, pack_key),
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    return counts

def archive_pack(pack_key: str) -> dict[str, int]:
    """Archive expansion packs while protecting the built-in core pack."""
    ensure_content_pack_tables()
    pack = load_pack(pack_key)
    if not pack.get("archive_allowed", pack.get("pack_type") != "core"):
        raise ValueError(
            "The built-in Default Family Pack cannot be archived as a whole. "
            "Its example Quest, Reward, and Adventure may be archived individually."
        )
    db = get_db()
    family_id = get_current_family_id()
    installation = db.execute(
        "SELECT status FROM family_content_packs WHERE family_id=? AND pack_key=?",
        (family_id, pack_key),
    ).fetchone()
    if not installation:
        raise ValueError("This Content Pack is not installed for your family.")
    if installation["status"] == "archived":
        raise ValueError("This Content Pack is already archived.")

    counts = {"quest": 0, "adventure": 0, "challenge": 0, "reward": 0, "achievement": 0, "cosmetic": 0}
    try:
        items = db.execute(
            "SELECT id,item_type,item_id,item_archived,pack_archived FROM content_pack_items WHERE family_id=? AND pack_key=?",
            (family_id, pack_key),
        ).fetchall()
        for item in items:
            # An item already archived individually stays archived and is not marked
            # for automatic restoration with the pack. Check the actual library state
            # so this works even before individual archive routes update pack metadata.
            if item["pack_archived"]:
                continue
            currently_active = _get_item_active(item["item_type"], item["item_id"], family_id)
            if currently_active is not True:
                continue
            changed = _set_item_active(item["item_type"], item["item_id"], family_id, False)
            if changed:
                db.execute("UPDATE content_pack_items SET pack_archived=1 WHERE id=?", (item["id"],))
                counts[item["item_type"]] = counts.get(item["item_type"], 0) + 1
        db.execute(
            "UPDATE family_content_packs SET status='archived',updated_at=CURRENT_TIMESTAMP WHERE family_id=? AND pack_key=?",
            (family_id, pack_key),
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return counts


def restore_pack(pack_key: str) -> dict[str, int]:
    """Restore only items archived by the pack, not items archived individually."""
    ensure_content_pack_tables()
    db = get_db()
    family_id = get_current_family_id()
    installation = db.execute(
        "SELECT status FROM family_content_packs WHERE family_id=? AND pack_key=?",
        (family_id, pack_key),
    ).fetchone()
    if not installation:
        raise ValueError("This Content Pack is not installed for your family.")
    if installation["status"] == "active":
        raise ValueError("This Content Pack is already active.")

    counts = {"quest": 0, "adventure": 0, "challenge": 0, "reward": 0, "achievement": 0, "cosmetic": 0}
    try:
        items = db.execute(
            """SELECT id,item_type,item_id,item_archived,pack_archived
               FROM content_pack_items WHERE family_id=? AND pack_key=? AND pack_archived=1""",
            (family_id, pack_key),
        ).fetchall()
        for item in items:
            if item["item_archived"]:
                # Retain deliberate individual archives.
                db.execute("UPDATE content_pack_items SET pack_archived=0 WHERE id=?", (item["id"],))
                continue
            changed = _set_item_active(item["item_type"], item["item_id"], family_id, True)
            db.execute("UPDATE content_pack_items SET pack_archived=0 WHERE id=?", (item["id"],))
            if changed:
                counts[item["item_type"]] = counts.get(item["item_type"], 0) + 1
        db.execute(
            "UPDATE family_content_packs SET status='active',updated_at=CURRENT_TIMESTAMP WHERE family_id=? AND pack_key=?",
            (family_id, pack_key),
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return counts



def get_pack_store_context(child_id: int | None = None, selected_filter: str = "all") -> dict:
    """Build the family Pack Store catalog for parent or family browse mode."""
    ensure_content_pack_tables()
    if selected_filter not in {"all", "free", "premium", "installed"}:
        selected_filter = "all"
    packs = discover_packs()
    family_id = get_current_family_id()
    child = None
    if child_id is not None:
        child = get_db().execute(
            "SELECT id,name FROM users WHERE id=? AND family_id=? AND role='child' AND active=1",
            (int(child_id), family_id),
        ).fetchone()
        if child is None:
            raise ValueError("Child profile not found.")
    family_requests = {
        row["pack_key"]: dict(row)
        for row in get_db().execute(
            "SELECT id,pack_key,status,requested_at,resolved_at FROM content_pack_requests WHERE family_id=?",
            (family_id,),
        ).fetchall()
    }
    for pack in packs:
        pack["family_request"] = family_requests.get(pack["id"])
        pack["price_label"] = "FREE" if pack.get("price_type", "free") == "free" else f"${int(pack.get('price_cents', 0)) / 100:.2f}"
    if selected_filter == "free":
        visible = [p for p in packs if p.get("price_type", "free") == "free"]
    elif selected_filter == "premium":
        visible = [p for p in packs if p.get("price_type") == "paid"]
    elif selected_filter == "installed":
        visible = [p for p in packs if p.get("installation")]
    else:
        visible = packs
    return {
        "packs": visible,
        "all_packs": packs,
        "selected_filter": selected_filter,
        "store_child": dict(child) if child else None,
        "store_summary": {
            "all": len(packs),
            "free": len([p for p in packs if p.get("price_type", "free") == "free"]),
            "premium": len([p for p in packs if p.get("price_type") == "paid"]),
            "installed": len([p for p in packs if p.get("installation") and p["installation"]["status"] == "active"]),
        },
    }


def request_pack(pack_key: str) -> dict:
    """Create or renew one family-level Content Pack request."""
    ensure_content_pack_tables()
    pack = load_pack(pack_key)
    if not pack.get("discoverable", True):
        raise ValueError("This Content Pack is not available in the Pack Store.")
    db = get_db()
    family_id = get_current_family_id()
    _register_pack_manifest(pack)
    installed = db.execute(
        "SELECT status FROM family_content_packs WHERE family_id=? AND pack_key=?",
        (family_id, pack_key),
    ).fetchone()
    if installed and installed["status"] == "active":
        raise ValueError("This Content Pack is already installed for your family.")
    existing = db.execute(
        "SELECT id,status FROM content_pack_requests WHERE family_id=? AND pack_key=?",
        (family_id, pack_key),
    ).fetchone()
    if existing and existing["status"] == "pending":
        raise ValueError("This request is already waiting for parent approval.")
    if existing:
        db.execute(
            "UPDATE content_pack_requests SET status='pending',requested_at=CURRENT_TIMESTAMP,resolved_at=NULL WHERE id=? AND family_id=?",
            (existing["id"], family_id),
        )
        request_id = int(existing["id"])
    else:
        request_id = int(db.execute(
            "INSERT INTO content_pack_requests(family_id,pack_key,status) VALUES(?,?,'pending')",
            (family_id, pack_key),
        ).lastrowid)
    db.commit()
    return {"id": request_id, "pack": pack}


def list_pending_pack_requests() -> list[dict]:
    """Return tenant-scoped family Pack Store requests for the Approval Center."""
    ensure_content_pack_tables()
    rows = get_db().execute(
        """SELECT pr.id,pr.pack_key,pr.requested_at,
                  cp.name AS title,cp.description,cp.icon,cp.price_type,cp.price_cents
           FROM content_pack_requests pr
           JOIN content_packs cp ON cp.pack_key=pr.pack_key
           WHERE pr.family_id=? AND pr.status='pending'
           ORDER BY pr.requested_at ASC,pr.id ASC""",
        (get_current_family_id(),),
    ).fetchall()
    results = []
    for row in rows:
        item = dict(row)
        item.update({
            "activity_kind": "pack_request",
            "type_label": "Pack Request",
            "completed_at": item["requested_at"],
            "price_label": "FREE" if item["price_type"] == "free" else f"${int(item['price_cents'] or 0) / 100:.2f}",
        })
        results.append(item)
    return results


def get_pack_request(request_id: int) -> dict | None:
    """Return one tenant-scoped family Pack Store request."""
    ensure_content_pack_tables()
    row = get_db().execute(
        """SELECT pr.id,pr.pack_key,pr.status,pr.requested_at,pr.resolved_at,
                  cp.name AS title,cp.description,cp.icon,cp.price_type,cp.price_cents
           FROM content_pack_requests pr
           JOIN content_packs cp ON cp.pack_key=pr.pack_key
           WHERE pr.id=? AND pr.family_id=?""",
        (int(request_id), get_current_family_id()),
    ).fetchone()
    return dict(row) if row else None


def approve_pack_request(request_id: int) -> dict | None:
    """Approve a free family pack request and install it for the family."""
    request_row = get_pack_request(request_id)
    if request_row is None or request_row["status"] != "pending":
        return None
    if request_row["price_type"] == "paid":
        raise ValueError("Paid Content Packs are not enabled yet.")
    installed = get_db().execute(
        "SELECT status FROM family_content_packs WHERE family_id=? AND pack_key=?",
        (get_current_family_id(), request_row["pack_key"]),
    ).fetchone()
    if installed and installed["status"] == "archived":
        counts = restore_pack(request_row["pack_key"])
    else:
        try:
            counts = install_pack(request_row["pack_key"])
        except ValueError as exc:
            if "already installed" not in str(exc).lower():
                raise
            counts = None
    db = get_db()
    db.execute(
        "UPDATE content_pack_requests SET status='approved',resolved_at=CURRENT_TIMESTAMP WHERE id=? AND family_id=? AND status='pending'",
        (int(request_id), get_current_family_id()),
    )
    db.commit()
    request_row["counts"] = counts
    return request_row


def deny_pack_request(request_id: int) -> dict | None:
    """Deny one tenant-scoped family Pack Store request."""
    request_row = get_pack_request(request_id)
    if request_row is None or request_row["status"] != "pending":
        return None
    db = get_db()
    db.execute(
        "UPDATE content_pack_requests SET status='denied',resolved_at=CURRENT_TIMESTAMP WHERE id=? AND family_id=? AND status='pending'",
        (int(request_id), get_current_family_id()),
    )
    db.commit()
    return request_row


def get_child_pack_statuses(child_id: int) -> list[dict]:
    """Return family-level Pack Store request results visible to any child."""
    ensure_content_pack_tables()
    rows = get_db().execute(
        """SELECT pr.pack_key,pr.status,pr.requested_at,pr.resolved_at,cp.name,cp.icon
           FROM content_pack_requests pr
           JOIN content_packs cp ON cp.pack_key=pr.pack_key
           WHERE pr.family_id=?
           ORDER BY COALESCE(pr.resolved_at,pr.requested_at) DESC""",
        (get_current_family_id(),),
    ).fetchall()
    return [dict(row) for row in rows]


_AVAILABLE_PACK_PREVIEWS = [
    {
        "id": "student_chef",
        "name": "Student Chef Adventure Pack",
        "icon": "🧑‍🍳",
        "category": "adventure",
        "description": "A focused cooking progression with kitchen safety, snack preparation, and cleanup skills.",
        "recommended_age": "7-12",
        "difficulty": "Beginner",
        "estimated_duration": "3-6 weeks",
        "skills": ["Cooking", "Safety", "Responsibility"],
        "status": "coming_soon",
    },
    {
        "id": "outdoor_explorer",
        "name": "Outdoor Explorer Pack",
        "icon": "🏕️",
        "category": "adventure",
        "description": "Outdoor observation, camp skills, stewardship, and family exploration activities.",
        "recommended_age": "6-12",
        "difficulty": "Beginner",
        "estimated_duration": "4-8 weeks",
        "skills": ["Nature", "Outdoor Skills", "Stewardship"],
        "status": "coming_soon",
    },
    {
        "id": "reading_adventures",
        "name": "Reading Adventures Pack",
        "icon": "📚",
        "category": "challenge",
        "description": "Reading quests, streak challenges, achievements, and family reading rewards.",
        "recommended_age": "5-12",
        "difficulty": "All Levels",
        "estimated_duration": "Ongoing",
        "skills": ["Reading", "Consistency", "Learning"],
        "status": "coming_soon",
    },
]


def get_available_pack_previews() -> list[dict]:
    """Retrieve available pack previews."""
    return [dict(item) for item in _AVAILABLE_PACK_PREVIEWS]


def get_pack_source_map(item_type: str, item_ids) -> dict[int, dict]:
    """Return source-pack metadata for family-owned library items."""
    ids = [int(value) for value in item_ids if value is not None]
    if not ids:
        return {}
    ensure_content_pack_tables()
    placeholders = ",".join("?" for _ in ids)
    rows = get_db().execute(
        f"""SELECT cpi.item_id, cp.pack_key, cp.name, cp.icon, fcp.status AS pack_status
            FROM content_pack_items cpi
            JOIN content_packs cp ON cp.pack_key=cpi.pack_key
            LEFT JOIN family_content_packs fcp
              ON fcp.family_id=cpi.family_id AND fcp.pack_key=cpi.pack_key
            WHERE cpi.family_id=? AND cpi.item_type=? AND cpi.item_id IN ({placeholders})""",
        (get_current_family_id(), item_type, *ids),
    ).fetchall()
    return {row["item_id"]: dict(row) for row in rows}


def get_pack_manager_context() -> dict:
    """Retrieve pack manager context."""
    packs = discover_packs()
    installed = [pack for pack in packs if pack.get("installation") and pack["installation"]["status"] == "active"]
    archived = [pack for pack in packs if pack.get("installation") and pack["installation"]["status"] == "archived"]
    family_id = get_current_family_id()
    db = get_db()
    type_counts = {
        row["item_type"]: row["total"]
        for row in db.execute(
            "SELECT item_type,COUNT(*) total FROM content_pack_items WHERE family_id=? GROUP BY item_type",
            (family_id,),
        ).fetchall()
    }
    summary = {
        "installed": len(installed),
        "archived": len(archived),
        "available": len([p for p in packs if not p.get("installation")]) + len(_AVAILABLE_PACK_PREVIEWS),
        "quests": type_counts.get("quest", 0),
        "adventures": type_counts.get("adventure", 0),
        "rewards": type_counts.get("reward", 0),
    }
    return {
        "packs": packs,
        "installed_packs": installed,
        "archived_packs": archived,
        "available_packs": [p for p in packs if not p.get("installation")],
        "preview_packs": get_available_pack_previews(),
        "summary": summary,
    }


def get_pack_detail(pack_key: str, child_id: int | None = None) -> dict:
    """Retrieve one Pack Store detail record for the active family."""
    ensure_content_pack_tables()
    pack = load_pack(pack_key)
    family_id = get_current_family_id()
    installation = get_db().execute(
        "SELECT installed_version,status,installed_at,updated_at FROM family_content_packs WHERE family_id=? AND pack_key=?",
        (family_id, pack_key),
    ).fetchone()
    pack["installation"] = dict(installation) if installation else None
    if child_id is not None:
        child = get_db().execute(
            "SELECT id FROM users WHERE id=? AND family_id=? AND role='child' AND active=1",
            (int(child_id), family_id),
        ).fetchone()
        if child is None:
            raise ValueError("Child profile not found.")
    row = get_db().execute(
        "SELECT id,status,requested_at,resolved_at FROM content_pack_requests WHERE family_id=? AND pack_key=?",
        (family_id, pack_key),
    ).fetchone()
    pack["family_request"] = dict(row) if row else None
    pack["price_label"] = "FREE" if pack.get("price_type", "free") == "free" else f"${int(pack.get('price_cents', 0)) / 100:.2f}"
    pack["counts"] = {key: len(pack.get(key, [])) for key in ("quests","adventures","challenges","rewards","achievements","avatars","frames","themes")}
    pack.setdefault("author", "Family Quest Center")
    pack.setdefault("difficulty", "Beginner")
    pack.setdefault("estimated_duration", "30-60 days")
    pack.setdefault("skills", ["Responsibility", "Independence", "Family Participation"])
    return pack



def get_platform_pack_diagnostics() -> dict:
    """Return installation-wide pack diagnostics for the Application Owner."""
    ensure_content_pack_tables()
    db = get_db()

    manifests = []
    validation = []
    for path in _manifest_paths():
        try:
            data = _validate_pack(
                json.loads(path.read_text(encoding="utf-8")),
                path,
            )
            if data.get("discoverable", True):
                manifests.append(data)
            validation.append({
                "file": str(path.relative_to(Path(current_app.root_path))),
                "status": "healthy",
                "detail": f"{data['name']} v{data['version']}",
            })
        except Exception as exc:
            validation.append({
                "file": str(path),
                "status": "error",
                "detail": str(exc),
            })

    installation_rows = db.execute(
        """SELECT fcp.pack_key, fcp.installed_version, fcp.status,
                  COUNT(*) AS family_count
           FROM family_content_packs fcp
           JOIN families f ON f.id=fcp.family_id
           WHERE f.status='active'
           GROUP BY fcp.pack_key, fcp.installed_version, fcp.status"""
    ).fetchall()

    by_key = {}
    for row in installation_rows:
        by_key.setdefault(row["pack_key"], []).append(dict(row))

    packs = []
    active_count = 0
    archived_count = 0
    update_count = 0
    installed_keys = set()

    for manifest in manifests:
        rows = by_key.get(manifest["id"], [])
        active_families = sum(
            int(row["family_count"])
            for row in rows
            if row["status"] == "active"
        )
        archived_families = sum(
            int(row["family_count"])
            for row in rows
            if row["status"] == "archived"
        )
        update_families = sum(
            int(row["family_count"])
            for row in rows
            if row["status"] == "active"
            and str(row["installed_version"]) != str(manifest["version"])
        )

        if rows:
            installed_keys.add(manifest["id"])
        active_count += active_families
        archived_count += archived_families
        update_count += update_families

        item = dict(manifest)
        item["installation"] = {
            "installed_version": "Multiple" if len(rows) > 1 else (
                rows[0]["installed_version"] if rows else None
            ),
            "status": "active" if active_families else (
                "archived" if archived_families else None
            ),
            "active_families": active_families,
            "archived_families": archived_families,
            "update_families": update_families,
        } if rows else None
        item["manager_status"] = (
            "update_available" if update_families
            else "installed" if active_families
            else "archived" if archived_families
            else "available"
        )
        packs.append(item)

    tracked = db.execute(
        """SELECT item_type, COUNT(*) total
           FROM content_pack_items
           GROUP BY item_type
           ORDER BY item_type"""
    ).fetchall()

    return {
        "packs": packs,
        "installed_count": len(installed_keys),
        "active_count": active_count,
        "archived_count": archived_count,
        "available_count": len([
            pack for pack in manifests if pack["id"] not in installed_keys
        ]),
        "update_count": update_count,
        "updates": [
            pack for pack in packs
            if pack["manager_status"] == "update_available"
        ],
        "validation": validation,
        "tracked_items": {
            row["item_type"]: row["total"] for row in tracked
        },
    }

def get_pack_diagnostics() -> dict:
    """Return a read-only diagnostic snapshot for discovered and installed packs."""
    ensure_content_pack_tables()
    db = get_db()
    family_id = get_current_family_id()
    packs = discover_packs()
    installed = [p for p in packs if p.get("installation")]
    active = [p for p in installed if p["installation"]["status"] == "active"]
    archived = [p for p in installed if p["installation"]["status"] == "archived"]
    updates = [
        p for p in active
        if str(p["installation"]["installed_version"]) != str(p["version"])
    ]
    validation = []
    for path in _manifest_paths():
        try:
            data = _validate_pack(json.loads(path.read_text(encoding="utf-8")), path)
            validation.append({"file": str(path.relative_to(Path(current_app.root_path))), "status": "healthy", "detail": f"{data['name']} v{data['version']}"})
        except Exception as exc:
            validation.append({"file": str(path), "status": "error", "detail": str(exc)})
    tracked = db.execute(
        "SELECT item_type, COUNT(*) total FROM content_pack_items WHERE family_id=? GROUP BY item_type ORDER BY item_type",
        (family_id,),
    ).fetchall()
    return {
        "packs": packs,
        "installed_count": len(installed),
        "active_count": len(active),
        "archived_count": len(archived),
        "available_count": len([p for p in packs if not p.get("installation")]),
        "update_count": len(updates),
        "updates": updates,
        "validation": validation,
        "tracked_items": {row["item_type"]: row["total"] for row in tracked},
    }
