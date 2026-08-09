"""Reward store, requests, and parent approval workflow."""

from __future__ import annotations

from datetime import datetime

from database import get_db
from models.economy import get_balance, spend_stars
from services.tenant_context import get_current_family_id


VALID_REQUEST_STATUSES = {"pending", "approved", "denied", "redeemed"}


def get_categories(include_inactive: bool = True):
    """Retrieve categories."""
    database = get_db()
    where = "WHERE family_id = ?" if include_inactive else "WHERE family_id = ? AND active = 1"
    return database.execute(
        f"SELECT * FROM reward_categories {where} ORDER BY display_order, name",
        (get_current_family_id(),),
    ).fetchall()


def create_category(name: str, icon: str, display_order: int = 0):
    """Create category."""
    database = get_db()
    database.execute(
        "INSERT INTO reward_categories (name, icon, display_order, active, family_id) VALUES (?, ?, ?, 1, ?)",
        (name.strip(), icon.strip() or "🎁", display_order, get_current_family_id()),
    )
    database.commit()


def set_category_active(category_id: int, active: bool):
    """Handle the set category active workflow."""
    database = get_db()
    database.execute(
        "UPDATE reward_categories SET active = ? WHERE id = ? AND family_id = ?",
        (1 if active else 0, category_id, get_current_family_id()),
    )
    database.commit()


def get_rewards(include_inactive: bool = True):
    """Retrieve rewards."""
    database = get_db()
    where = "WHERE rewards.family_id = ?" if include_inactive else "WHERE rewards.family_id = ? AND rewards.active = 1"
    return database.execute(
        f"""
        SELECT rewards.*, reward_categories.name AS category_name,
               reward_categories.icon AS category_icon
        FROM rewards
        LEFT JOIN reward_categories ON reward_categories.id = rewards.category_id
        {where}
        ORDER BY rewards.active DESC, reward_categories.display_order,
                 reward_categories.name, rewards.name
        """,
        (get_current_family_id(),),
    ).fetchall()


def get_shop_rewards():
    """Return active rewards whose category is also available."""
    return get_db().execute(
        """
        SELECT rewards.*, reward_categories.name AS category_name,
               reward_categories.icon AS category_icon
        FROM rewards
        LEFT JOIN reward_categories ON reward_categories.id = rewards.category_id
        WHERE rewards.active = 1
          AND rewards.family_id = ?
          AND (reward_categories.id IS NULL OR reward_categories.active = 1)
          AND (rewards.quantity IS NULL OR rewards.quantity > 0)
        ORDER BY COALESCE(reward_categories.display_order, 999),
                 reward_categories.name, rewards.cost, rewards.name
        """,
        (get_current_family_id(),),
    ).fetchall()


def get_reward(reward_id: int, database=None):
    """Retrieve reward."""
    database = database or get_db()
    return database.execute(
        """
        SELECT rewards.*, reward_categories.name AS category_name,
               reward_categories.icon AS category_icon,
               reward_categories.active AS category_active
        FROM rewards
        LEFT JOIN reward_categories ON reward_categories.id = rewards.category_id
        WHERE rewards.id = ? AND rewards.family_id = ?
        """,
        (reward_id, get_current_family_id()),
    ).fetchone()


def save_reward(
    reward_id: int | None,
    category_id: int | None,
    name: str,
    description: str,
    icon: str,
    cost: int,
    quantity: int | None,
    requires_approval: bool,
    active: bool,
    image_filename: str | None = None,
):
    """Handle the save reward workflow."""
    database = get_db()
    values = (
        category_id, name.strip(), description.strip(), icon.strip() or "🎁",
        int(cost), quantity, 1 if requires_approval else 0,
        1 if active else 0, image_filename,
    )
    if reward_id:
        database.execute(
            """
            UPDATE rewards SET category_id=?, name=?, description=?, icon=?,
                cost=?, quantity=?, requires_approval=?, active=?,
                image_filename=COALESCE(?, image_filename),
                updated_at=CURRENT_TIMESTAMP
            WHERE id=? AND family_id=?
            """,
            values + (reward_id, get_current_family_id()),
        )
    else:
        database.execute(
            """
            INSERT INTO rewards (
                category_id, name, description, icon, cost, quantity,
                requires_approval, active, image_filename, family_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            values + (get_current_family_id(),),
        )
    database.commit()


def remove_reward_image(reward_id: int):
    """Handle the remove reward image workflow."""
    database = get_db()
    database.execute(
        "UPDATE rewards SET image_filename=NULL, updated_at=CURRENT_TIMESTAMP WHERE id=? AND family_id=?",
        (reward_id, get_current_family_id()),
    )
    database.commit()


def set_reward_active(reward_id: int, active: bool):
    """Handle the set reward active workflow."""
    database = get_db()
    database.execute(
        "UPDATE rewards SET active=?, updated_at=CURRENT_TIMESTAMP WHERE id=? AND family_id=?",
        (1 if active else 0, reward_id, get_current_family_id()),
    )
    database.commit()


def _reward_is_available(reward) -> bool:
    """Handle the reward is available workflow."""
    return bool(
        reward
        and reward["active"]
        and (reward["category_active"] is None or reward["category_active"])
        and (reward["quantity"] is None or int(reward["quantity"]) > 0)
    )


def create_reward_request(child_id: int, reward_id: int) -> tuple[bool, str, int | None]:
    """Create a pending request or immediately approve an automatic reward."""
    database = get_db()
    try:
        database.execute("BEGIN IMMEDIATE")
        reward = get_reward(reward_id, database)
        if not _reward_is_available(reward):
            database.rollback()
            return False, "That reward is no longer available.", None

        balance = get_balance(child_id, database)
        if balance < int(reward["cost"]):
            database.rollback()
            return False, f"You need {int(reward['cost']) - balance} more stars.", None

        existing = database.execute(
            """
            SELECT id FROM reward_requests
            WHERE child_id=? AND reward_id=? AND status='pending' AND family_id=?
            LIMIT 1
            """,
            (child_id, reward_id, get_current_family_id()),
        ).fetchone()
        if existing:
            database.rollback()
            return False, "You already have a pending request for this reward.", existing["id"]

        now = datetime.now().isoformat()
        status = "pending" if reward["requires_approval"] else "approved"
        cursor = database.execute(
            """
            INSERT INTO reward_requests (
                reward_id, child_id, status, requested_at, approved_at, family_id
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (reward_id, child_id, status, now, now if status == "approved" else None, get_current_family_id()),
        )
        request_id = int(cursor.lastrowid)

        if status == "approved":
            spend_stars(
                database, child_id, int(reward["cost"]),
                f"Reward: {reward['name']}", reference_type="REWARD_REQUEST",
                reference_id=request_id,
                idempotency_key=f"reward-request-spend:{request_id}",
            )
            if reward["quantity"] is not None:
                database.execute(
                    "UPDATE rewards SET quantity=quantity-1, updated_at=CURRENT_TIMESTAMP WHERE id=? AND family_id=? AND quantity>0",
                    (reward_id, get_current_family_id()),
                )

        database.commit()
        if status == "approved":
            return True, "Reward purchased! Show this approval to your parent.", request_id
        return True, "Reward request sent to your parent.", request_id
    except Exception:
        database.rollback()
        raise


def get_reward_requests(
    child_id: int | None = None,
    status: str | None = None,
    limit: int | None = None,
):
    """Retrieve reward requests."""
    database = get_db()
    clauses, values = ["reward_requests.family_id = ?"], [get_current_family_id()]
    if child_id is not None:
        clauses.append("reward_requests.child_id = ?")
        values.append(child_id)
    if status in VALID_REQUEST_STATUSES:
        clauses.append("reward_requests.status = ?")
        values.append(status)
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    limit_sql = "LIMIT ?" if limit else ""
    if limit:
        values.append(limit)
    return database.execute(
        f"""
        SELECT reward_requests.*, rewards.name AS reward_name,
               rewards.description AS reward_description,
               rewards.icon AS reward_icon, rewards.image_filename,
               rewards.cost, users.name AS child_name
        FROM reward_requests
        JOIN rewards ON rewards.id = reward_requests.reward_id
        JOIN users ON users.id = reward_requests.child_id
        {where}
        ORDER BY CASE reward_requests.status WHEN 'pending' THEN 0 ELSE 1 END,
                 reward_requests.requested_at DESC, reward_requests.id DESC
        {limit_sql}
        """,
        tuple(values),
    ).fetchall()


def get_request(request_id: int, database=None):
    """Retrieve request."""
    database = database or get_db()
    return database.execute(
        """
        SELECT reward_requests.*, rewards.name AS reward_name,
               rewards.icon AS reward_icon, rewards.cost, rewards.quantity,
               rewards.active AS reward_active, rewards.category_id,
               reward_categories.active AS category_active,
               users.name AS child_name
        FROM reward_requests
        JOIN rewards ON rewards.id=reward_requests.reward_id
        LEFT JOIN reward_categories ON reward_categories.id=rewards.category_id
        JOIN users ON users.id=reward_requests.child_id
        WHERE reward_requests.id=? AND reward_requests.family_id=?
        """,
        (request_id, get_current_family_id()),
    ).fetchone()


def approve_request(request_id: int, approved_by: int | None = None, notes: str = "") -> tuple[bool, str]:
    """Handle the approve request workflow."""
    database = get_db()
    try:
        database.execute("BEGIN IMMEDIATE")
        reward_request = get_request(request_id, database)
        if reward_request is None:
            database.rollback()
            return False, "Reward request was not found."
        if reward_request["status"] != "pending":
            database.rollback()
            return False, "That request has already been processed."
        if not reward_request["reward_active"] or (
            reward_request["category_active"] is not None and not reward_request["category_active"]
        ):
            database.rollback()
            return False, "That reward is no longer active."
        if reward_request["quantity"] is not None and int(reward_request["quantity"]) <= 0:
            database.rollback()
            return False, "That reward is out of stock."
        if get_balance(reward_request["child_id"], database) < int(reward_request["cost"]):
            database.rollback()
            return False, f"{reward_request['child_name']} no longer has enough stars."

        spend_stars(
            database, reward_request["child_id"], int(reward_request["cost"]),
            f"Reward: {reward_request['reward_name']}",
            reference_type="REWARD_REQUEST", reference_id=request_id,
            idempotency_key=f"reward-request-spend:{request_id}",
        )
        if reward_request["quantity"] is not None:
            database.execute(
                "UPDATE rewards SET quantity=quantity-1, updated_at=CURRENT_TIMESTAMP WHERE id=? AND family_id=? AND quantity>0",
                (reward_request["reward_id"], get_current_family_id()),
            )
        database.execute(
            """
            UPDATE reward_requests
            SET status='approved', approved_at=?, approved_by=?, notes=?
            WHERE id=? AND status='pending' AND family_id=?
            """,
            (datetime.now().isoformat(), approved_by, notes.strip(), request_id, get_current_family_id()),
        )
        database.commit()
        return True, f"Approved {reward_request['reward_name']} for {reward_request['child_name']}."
    except Exception:
        database.rollback()
        raise


def deny_request(request_id: int, approved_by: int | None = None, notes: str = "") -> tuple[bool, str]:
    """Handle the deny request workflow."""
    database = get_db()
    cursor = database.execute(
        """
        UPDATE reward_requests
        SET status='denied', denied_at=?, approved_by=?, notes=?
        WHERE id=? AND status='pending' AND family_id=?
        """,
        (datetime.now().isoformat(), approved_by, notes.strip(), request_id, get_current_family_id()),
    )
    database.commit()
    if cursor.rowcount != 1:
        return False, "That request has already been processed or was not found."
    return True, "Reward request denied."


def mark_redeemed(request_id: int) -> tuple[bool, str]:
    """Handle the mark redeemed workflow."""
    database = get_db()
    cursor = database.execute(
        """
        UPDATE reward_requests SET status='redeemed', redeemed_at=?
        WHERE id=? AND status='approved' AND family_id=?
        """,
        (datetime.now().isoformat(), request_id, get_current_family_id()),
    )
    database.commit()
    if cursor.rowcount != 1:
        return False, "Only approved rewards can be marked redeemed."
    return True, "Reward marked as redeemed."
