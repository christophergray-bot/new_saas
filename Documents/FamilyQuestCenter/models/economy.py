"""Ledger-based star economy for Family Quest Center."""

from __future__ import annotations

from datetime import datetime

from database import get_db


def get_balance(user_id: int, database=None) -> int:
    """Return the user's current star balance from the permanent ledger."""
    database = database or get_db()
    row = database.execute(
        "SELECT COALESCE(SUM(amount), 0) AS balance FROM star_transactions WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    return int(row["balance"] or 0)


def record_transaction(
    database,
    user_id: int,
    amount: int,
    transaction_type: str,
    description: str,
    reference_type: str | None = None,
    reference_id: int | None = None,
    idempotency_key: str | None = None,
) -> int | None:
    """Record one ledger entry and synchronize users.total_points.

    Returns the new transaction id. If the idempotency key already exists,
    no duplicate entry is created and None is returned.
    """
    amount = int(amount)
    if amount == 0:
        raise ValueError("Star transaction amount cannot be zero.")

    if amount < 0 and get_balance(user_id, database) + amount < 0:
        raise ValueError("This child does not have enough stars.")

    cursor = database.execute(
        """
        INSERT OR IGNORE INTO star_transactions (
            user_id, amount, transaction_type, reference_type,
            reference_id, description, idempotency_key, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            amount,
            transaction_type.upper(),
            reference_type.upper() if reference_type else None,
            reference_id,
            description,
            idempotency_key,
            datetime.now().isoformat(),
        ),
    )
    if cursor.rowcount != 1:
        return None

    balance = get_balance(user_id, database)
    database.execute(
        "UPDATE users SET total_points = ? WHERE id = ?",
        (balance, user_id),
    )
    return int(cursor.lastrowid)


def award_stars(database, user_id: int, amount: int, description: str, **kwargs):
    """Handle the award stars workflow."""
    if amount <= 0:
        raise ValueError("Star award must be greater than zero.")
    return record_transaction(database, user_id, amount, "EARN", description, **kwargs)


def spend_stars(database, user_id: int, amount: int, description: str, **kwargs):
    """Handle the spend stars workflow."""
    if amount <= 0:
        raise ValueError("Star cost must be greater than zero.")
    return record_transaction(database, user_id, -amount, "SPEND", description, **kwargs)


def refund_stars(database, user_id: int, amount: int, description: str, **kwargs):
    """Handle the refund stars workflow."""
    if amount <= 0:
        raise ValueError("Star refund must be greater than zero.")
    return record_transaction(database, user_id, amount, "REFUND", description, **kwargs)


def get_recent_transactions(user_id: int, limit: int = 20):
    """Retrieve recent transactions."""
    database = get_db()
    return database.execute(
        """
        SELECT * FROM star_transactions
        WHERE user_id = ?
        ORDER BY created_at DESC, id DESC
        LIMIT ?
        """,
        (user_id, limit),
    ).fetchall()
