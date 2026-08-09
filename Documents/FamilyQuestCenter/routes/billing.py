"""Stripe-hosted subscription checkout and billing management routes."""
from __future__ import annotations

from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for

from services.account_auth import account_required, get_current_membership
from services.billing import process_webhook_event, stripe_client, subscription_for_family, sync_subscription_for_family, verify_checkout_session

billing_blueprint = Blueprint("billing", __name__, url_prefix="/billing")


def _configured() -> bool:
    return bool(current_app.config.get("STRIPE_SECRET_KEY") and current_app.config.get("STRIPE_PRICE_ID"))


@billing_blueprint.route("/", strict_slashes=False)
def plans():
    return render_template("billing/plans.html", stripe_configured=_configured(), payments_mode=current_app.config.get("PAYMENTS_MODE"))


@billing_blueprint.route("/checkout", methods=["POST"])
def create_checkout():
    if not _configured():
        flash("Stripe test billing is not configured yet.", "error")
        return redirect(url_for("billing.plans"))
    stripe = stripe_client()
    checkout = stripe.checkout.Session.create(
        mode="subscription",
        line_items=[{"price": current_app.config["STRIPE_PRICE_ID"], "quantity": 1}],
        success_url=url_for("billing.success", _external=True) + "?session_id={CHECKOUT_SESSION_ID}",
        cancel_url=url_for("billing.cancel", _external=True),
        allow_promotion_codes=True,
    )
    return redirect(checkout.url, code=303)


@billing_blueprint.route("/success")
def success():
    session_id = request.args.get("session_id", "").strip()
    if not session_id:
        flash("The Stripe checkout session was missing.", "error")
        return redirect(url_for("billing.plans"))
    try:
        entitlement = verify_checkout_session(session_id)
    except Exception:
        current_app.logger.exception("Unable to verify Stripe Checkout session")
        flash("We could not confirm the subscription yet. Refresh this page in a moment.", "warning")
        return render_template("billing/success.html", confirmed=False)
    session["billing_entitlement"] = entitlement
    return render_template("billing/success.html", confirmed=True, email=entitlement["email"])


@billing_blueprint.route("/cancel")
def cancel():
    return render_template("billing/cancel.html")


@billing_blueprint.route("/portal", methods=["POST"])
@account_required
def portal():
    membership = get_current_membership()
    record = subscription_for_family(int(membership["family_id"]))
    if not record or not record["stripe_customer_id"]:
        flash("No Stripe billing profile is connected to this family.", "warning")
        return redirect(url_for("billing.status"))
    stripe = stripe_client()
    portal_session = stripe.billing_portal.Session.create(
        customer=record["stripe_customer_id"],
        return_url=url_for("billing.status", _external=True),
    )
    return redirect(portal_session.url, code=303)


@billing_blueprint.route("/status")
@account_required
def status():
    membership = get_current_membership()
    family_id = int(membership["family_id"])
    try:
        subscription = sync_subscription_for_family(family_id)
    except Exception:
        current_app.logger.exception("Unable to refresh subscription status from Stripe")
        subscription = subscription_for_family(family_id)
    return render_template("billing/status.html", subscription=subscription)


@billing_blueprint.route("/webhook", methods=["POST"])
def webhook():
    stripe = stripe_client()
    payload = request.get_data(cache=False)
    signature = request.headers.get("Stripe-Signature", "")
    secret = current_app.config.get("STRIPE_WEBHOOK_SECRET", "")
    if not secret:
        return "Webhook secret not configured", 503
    try:
        event = stripe.Webhook.construct_event(payload, signature, secret)
    except (ValueError, stripe.error.SignatureVerificationError):
        return "Invalid webhook", 400
    process_webhook_event(event)
    return "", 200
