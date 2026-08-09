# Application Owner Sprint 1 — Role Separation

Implemented for the clean-install workflow:

- The first setup creates a platform-only `application_owner` account.
- No family, family membership, family PIN, starter content, or billing record is created for the Application Owner.
- Application Owner sign-in routes directly to the owner/developer dashboard.
- Normal family registration remains separate and creates normal `platform_role=none` accounts.
- Family routes continue to require an active family membership.
- Installation-level Developer and Backup/Restore tools accept the platform owner without requiring family membership.
- The application shell displays owner-only navigation when the signed-in account has no family membership.

## Clean-install requirement

This sprint is intended for a fresh database/volume. Existing installations that used the first family owner as the installation owner should be migrated deliberately rather than automatically converting that family account.
