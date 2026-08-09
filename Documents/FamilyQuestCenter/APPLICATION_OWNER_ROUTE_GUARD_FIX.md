# Application Owner Route Guard Fix

## Problem
The Application Owner session was valid, but the global parent-security middleware required every signed-in account to have an active family membership before allowing `/developer` and `/maintenance` routes. Because the separated Application Owner intentionally has no family membership, owner dashboard links redirected back to account login.

## Resolution
- Platform-only `developer.*` routes now require an authenticated account at the global boundary and defer owner authorization to the Developer blueprint.
- `maintenance.*` routes now defer to their existing route decorators:
  - `installation_owner_required` for database backup, restore, and integrity tools.
  - `roles_required` for family-scoped export tools.
- Family-facing routes continue to require an active family membership and Parent PIN where applicable.
- Added a regression test confirming a platform-only Application Owner can open `/developer/` without a family membership.

## Security result
This does not grant normal parents access to owner tools. The Developer blueprint still returns 403 unless the account is the designated Application Owner, and maintenance routes retain their existing role-specific decorators.
