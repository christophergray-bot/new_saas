# Phase 2 Registration Lifecycle

## Fresh installation
1. A fresh database contains no Application Owner and no customer family.
2. `/account/register` redirects to `/account/setup-owner`.
3. The one-time setup creates a platform-only `application_owner` account.
4. No family, family membership, PIN, starter pack, subscription, or billing record is created.
5. The Application Owner is sent to the Owner Dashboard.

## Registration control
1. The Application Owner controls the installation-wide registration mode from System Settings.
2. Closed mode blocks new family registration while allowing existing families to sign in.
3. Local, open, and trial modes permit the family registration workflow according to configuration.

## Customer family registration
1. An ordinary customer visits the billing plan when Stripe checkout is configured.
2. After a successful test/live checkout entitlement, the customer enters `/account/register`.
3. Family registration creates a normal account with `platform_role = none`, an active family, and an owner membership.
4. The selected starter experience is installed for that family only.
5. The checkout entitlement is attached to the new family and account.
6. The parent continues to the Family PIN/onboarding workflow and then the Parent Dashboard.

## Separation rules
- Application Owner setup and customer family registration are different workflows.
- The Application Owner is never billed and never receives starter family content.
- Customer families never receive platform-owner privileges.
- Tests must create the Application Owner before testing family registration.
