# Application Owner Sprint 1 — Registration Test Update

Updated after the first local regression run on 2026-08-05.

## Why ten tests failed
The affected tests assumed that `/account/register` creates the first account and first family. The new architecture intentionally redirects a fresh installation to `/account/setup-owner` first.

## Corrections
- Account recovery tests now create a platform-only Application Owner, clear that browser session, and then register a normal family owner.
- Starter Content Pack tests now create the Application Owner before testing customer family registration.
- Stripe registration tests now create the Application Owner before checking the billing redirect.
- The full setup, registration, billing, starter-pack, and onboarding lifecycle is documented in `PHASE2_REGISTRATION_LIFECYCLE.md`.

## Expected test behavior
- Fresh `/account/register` redirects to `/account/setup-owner`.
- After owner setup, ordinary family registration is available when registration mode permits it.
- Stripe-configured family registration redirects to billing.
- Starter Content Packs install only during normal family registration.
- Account recovery and Parent Two invitation tests operate on normal family accounts, not the Application Owner account.
