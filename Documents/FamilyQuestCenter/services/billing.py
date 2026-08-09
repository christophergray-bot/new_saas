"""Stripe Checkout subscription integration for Family Quest Center."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from flask import current_app

from database import get_db

ACTIVE_STATUSES = {"active", "trialing"}
GRACE_STATUSES = {"past_due"}


def stripe_client():
    try:
        import stripe
    except ImportError as exc:
        raise RuntimeError("The Stripe Python package is not installed.") from exc
    stripe.api_key = current_app.config.get("STRIPE_SECRET_KEY", "")
    if not stripe.api_key:
        raise RuntimeError("STRIPE_SECRET_KEY is not configured.")
    return stripe


def ensure_billing_schema() -> None:
    db = get_db()
    db.execute("""CREATE TABLE IF NOT EXISTS family_subscriptions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        family_id INTEGER UNIQUE,
        account_user_id INTEGER,
        stripe_customer_id TEXT UNIQUE,
        stripe_subscription_id TEXT UNIQUE,
        stripe_checkout_session_id TEXT UNIQUE,
        customer_email TEXT,
        status TEXT NOT NULL DEFAULT 'incomplete',
        current_period_end TEXT,
        cancel_at_period_end INTEGER NOT NULL DEFAULT 0,
        cancel_at TEXT,
        grace_until TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""")
    columns = {row[1] for row in db.execute("PRAGMA table_info(family_subscriptions)")}
    if "cancel_at" not in columns:
        db.execute("ALTER TABLE family_subscriptions ADD COLUMN cancel_at TEXT")
    db.execute("""CREATE TABLE IF NOT EXISTS stripe_webhook_events (
        event_id TEXT PRIMARY KEY,
        event_type TEXT NOT NULL,
        processed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""")
    db.commit()


def _iso_from_unix(value):
    if not value:
        return None
    return datetime.fromtimestamp(int(value), tz=timezone.utc).isoformat(timespec="seconds")


def verify_checkout_session(session_id: str) -> dict:
    stripe = stripe_client()
    checkout = _stripe_to_plain(
        stripe.checkout.Session.retrieve(session_id, expand=["subscription"])
    )
    if not isinstance(checkout, dict):
        raise TypeError("Stripe Checkout session could not be converted to a dictionary.")
    if checkout.get("mode") != "subscription":
        raise ValueError("Checkout session is not a subscription.")

    subscription = checkout.get("subscription")
    if isinstance(subscription, dict):
        subscription_id = subscription.get("id")
        status = subscription.get("status")
        period_end = subscription.get("current_period_end")
        if period_end is None:
            items = ((subscription.get("items") or {}).get("data") or [])
            if items:
                period_end = items[0].get("current_period_end")
        cancel_at_period_end = int(bool(subscription.get("cancel_at_period_end")))
    else:
        subscription_id = subscription
        status = None
        period_end = None
        cancel_at_period_end = 0

    payment_status = checkout.get("payment_status")
    if status not in ACTIVE_STATUSES and payment_status != "paid":
        raise ValueError("Subscription payment has not been confirmed.")

    details = checkout.get("customer_details") or {}
    return {
        "checkout_session_id": checkout.get("id"),
        "customer_id": checkout.get("customer"),
        "subscription_id": subscription_id,
        "status": status or "active",
        "email": (details.get("email") or checkout.get("customer_email") or "").lower(),
        "current_period_end": _iso_from_unix(period_end),
        "cancel_at_period_end": cancel_at_period_end,
    }


def attach_checkout_to_family(entitlement: dict, family_id: int, account_user_id: int) -> None:
    ensure_billing_schema()
    db = get_db()
    db.execute("""INSERT INTO family_subscriptions(
        family_id,account_user_id,stripe_customer_id,stripe_subscription_id,
        stripe_checkout_session_id,customer_email,status,current_period_end,cancel_at_period_end,updated_at
    ) VALUES(?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)
    ON CONFLICT(stripe_checkout_session_id) DO UPDATE SET
        family_id=excluded.family_id,account_user_id=excluded.account_user_id,
        stripe_customer_id=excluded.stripe_customer_id,stripe_subscription_id=excluded.stripe_subscription_id,
        customer_email=excluded.customer_email,status=excluded.status,
        current_period_end=excluded.current_period_end,cancel_at_period_end=excluded.cancel_at_period_end,
        updated_at=CURRENT_TIMESTAMP""", (
        family_id, account_user_id, entitlement["customer_id"], entitlement["subscription_id"],
        entitlement["checkout_session_id"], entitlement["email"], entitlement["status"],
        entitlement["current_period_end"], entitlement["cancel_at_period_end"],
    ))
    db.commit()


def subscription_for_family(family_id: int):
    ensure_billing_schema()
    return get_db().execute("SELECT * FROM family_subscriptions WHERE family_id=?", (family_id,)).fetchone()


def family_has_access(family_id: int) -> bool:
    row = subscription_for_family(family_id)
    if row is None:
        return False
    if row["status"] in ACTIVE_STATUSES:
        return True
    if row["status"] in GRACE_STATUSES and row["grace_until"]:
        try:
            grace = datetime.fromisoformat(row["grace_until"])
            if grace.tzinfo is None:
                grace = grace.replace(tzinfo=timezone.utc)
            return grace > datetime.now(timezone.utc)
        except ValueError:
            return False
    return False


def _upsert_subscription(*, customer_id, subscription_id, status, period_end=None, cancel_at_period_end=None, cancel_at=None):
    ensure_billing_schema()
    db = get_db()
    grace_until = None
    if status == "past_due":
        grace_until = (datetime.now(timezone.utc) + timedelta(days=current_app.config.get("SUBSCRIPTION_GRACE_DAYS", 7))).isoformat(timespec="seconds")
    cancel_value = None if cancel_at_period_end is None else int(bool(cancel_at_period_end))
    db.execute("""UPDATE family_subscriptions SET
        status=?,
        current_period_end=COALESCE(?, current_period_end),
        cancel_at_period_end=COALESCE(?, cancel_at_period_end),
        cancel_at=COALESCE(?, cancel_at),
        grace_until=?,
        updated_at=CURRENT_TIMESTAMP
        WHERE stripe_subscription_id=? OR stripe_customer_id=?""", (
        status, period_end, cancel_value, cancel_at, grace_until, subscription_id, customer_id,
    ))
    db.commit()


def sync_subscription_for_family(family_id: int):
    """Refresh the local subscription row from Stripe before displaying billing status."""
    record = subscription_for_family(family_id)
    if record is None or not record["stripe_subscription_id"]:
        return record

    stripe = stripe_client()
    subscription = _stripe_to_plain(
        stripe.Subscription.retrieve(record["stripe_subscription_id"])
    )
    if not isinstance(subscription, dict):
        return record

    period_end = subscription.get("current_period_end")
    if period_end is None:
        items = ((subscription.get("items") or {}).get("data") or [])
        if items:
            period_end = items[0].get("current_period_end")

    _upsert_subscription(
        customer_id=subscription.get("customer"),
        subscription_id=subscription.get("id"),
        status=subscription.get("status", record["status"]),
        period_end=_iso_from_unix(period_end),
        cancel_at_period_end=subscription.get("cancel_at_period_end", False),
        cancel_at=_iso_from_unix(subscription.get("cancel_at")),
    )
    return subscription_for_family(family_id)


def _stripe_to_plain(value):
    """Convert StripeObject values into ordinary nested Python containers."""
    if isinstance(value, dict):
        return {key: _stripe_to_plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_stripe_to_plain(item) for item in value]

    # StripeObject stores its fields in _data. Reading that directly avoids
    # treating newer Stripe objects as sequences (which caused KeyError: 0).
    stripe_data = getattr(value, "_data", None)
    if isinstance(stripe_data, dict):
        return {key: _stripe_to_plain(item) for key, item in stripe_data.items()}

    return value


def process_webhook_event(event) -> None:
    # stripe.Webhook.construct_event returns a Stripe Event object in newer SDKs.
    event = _stripe_to_plain(event)
    if not isinstance(event, dict):
        raise TypeError("Stripe webhook event could not be converted to a dictionary")

    ensure_billing_schema()
    db = get_db()
    event_id = event.get("id")
    if db.execute("SELECT 1 FROM stripe_webhook_events WHERE event_id=?", (event_id,)).fetchone():
        return
    event_type = event.get("type")
    obj = event["data"]["object"]
    if event_type == "checkout.session.completed":
        db.execute("""INSERT INTO family_subscriptions(
            stripe_customer_id,stripe_subscription_id,stripe_checkout_session_id,customer_email,status,updated_at
        ) VALUES(?,?,?,?,?,CURRENT_TIMESTAMP)
        ON CONFLICT(stripe_checkout_session_id) DO UPDATE SET
            stripe_customer_id=excluded.stripe_customer_id,stripe_subscription_id=excluded.stripe_subscription_id,
            customer_email=excluded.customer_email,status=excluded.status,updated_at=CURRENT_TIMESTAMP""", (
            obj.get("customer"), obj.get("subscription"), obj.get("id"),
            ((obj.get("customer_details") or {}).get("email") or obj.get("customer_email") or "").lower(),
            "active" if obj.get("payment_status") == "paid" else "incomplete",
        ))
    elif event_type in {"customer.subscription.created", "customer.subscription.updated", "customer.subscription.deleted"}:
        status = "canceled" if event_type.endswith("deleted") else obj.get("status", "incomplete")
        period_end = obj.get("current_period_end")
        if period_end is None:
            items = ((obj.get("items") or {}).get("data") or [])
            if items:
                period_end = items[0].get("current_period_end")
        _upsert_subscription(customer_id=obj.get("customer"), subscription_id=obj.get("id"), status=status,
            period_end=_iso_from_unix(period_end), cancel_at_period_end=obj.get("cancel_at_period_end", False),
            cancel_at=_iso_from_unix(obj.get("cancel_at")))
    elif event_type == "invoice.payment_failed":
        _upsert_subscription(customer_id=obj.get("customer"), subscription_id=obj.get("subscription"), status="past_due")
    elif event_type == "invoice.paid":
        _upsert_subscription(customer_id=obj.get("customer"), subscription_id=obj.get("subscription"), status="active")
    db.execute("INSERT INTO stripe_webhook_events(event_id,event_type) VALUES(?,?)", (event_id, event_type))
    db.commit()
