# Phase 2 Stripe Registration Test Fix

The remaining Stripe test copied the seeded `chorce.db` fixture. That fixture already contains account rows, so the production-only `/account/setup-owner` route correctly returned HTTP 403.

The test helper now:

- Uses the normal setup route when the database is truly empty.
- Seeds an Application Owner directly only when the test fixture already contains accounts.
- Leaves the production setup restriction unchanged.

This preserves the rule that Application Owner setup is only available before any account exists while allowing billing regression tests to use the seeded database fixture.
