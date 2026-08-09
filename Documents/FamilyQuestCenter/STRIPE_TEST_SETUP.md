# Stripe Test Subscription Setup

This build includes Stripe-hosted Checkout, subscription webhooks, registration gating, a seven-day past-due grace period, account locking, and the Stripe Customer Portal.

## 1. Railway variables for sandbox testing

Set these variables using values from the Stripe **sandbox/test environment**:

```text
PAYMENTS_MODE=test
STRIPE_SECRET_KEY=sk_test_...
STRIPE_PUBLISHABLE_KEY=pk_test_...
STRIPE_PRICE_ID=price_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_ENFORCE_SUBSCRIPTIONS=true
SUBSCRIPTION_GRACE_DAYS=7
FAMILY_QUEST_REGISTRATION_MODE=open
APP_URL=https://your-current-family-quest-center-domain
```

Keep `STRIPE_ENFORCE_SUBSCRIPTIONS=false` during the first deployment if the existing test family does not yet have a Stripe subscription. Turn it on after completing one successful checkout and attaching the new test account.

## 2. Stripe webhook

In Stripe sandbox, create a webhook endpoint:

```text
https://your-domain/billing/webhook
```

Subscribe it to:

- `checkout.session.completed`
- `customer.subscription.created`
- `customer.subscription.updated`
- `customer.subscription.deleted`
- `invoice.paid`
- `invoice.payment_failed`

Copy the endpoint signing secret into `STRIPE_WEBHOOK_SECRET`.

## 3. Customer Portal

Enable the Stripe Customer Portal in sandbox. Allow customers to update payment methods and cancel subscriptions. Family Quest Center creates a short-lived portal session from **Billing & Subscription**.

## 4. Test flow

1. Open `/billing/`.
2. Select **Continue to Secure Checkout**.
3. Use Stripe's test card `4242 4242 4242 4242`, any future expiration date, and any CVC.
4. After Stripe redirects back, select **Create Your Family Account**.
5. The Stripe checkout email is locked into registration.
6. Complete Parent PIN and onboarding.
7. Open `/billing/status` and test the Customer Portal.

## 5. Safety switch

`PAYMENTS_MODE=test` labels the membership screen as test mode. Real charges require live Stripe keys and a live price. Do not mix test and live keys, prices, or webhook secrets.

`STRIPE_ENFORCE_SUBSCRIPTIONS` is the access-control switch:

- `false`: billing can be tested without locking existing families.
- `true`: families without an active/trialing subscription are redirected to Billing. Past-due accounts retain access through the configured grace period.

## 6. Before live launch

Create a live Stripe product, recurring price, and webhook endpoint. Replace all test values with live values and change `PAYMENTS_MODE=live`. Complete a low-value live end-to-end test before public registration opens.
