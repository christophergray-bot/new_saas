# Installation Owner Backup Permission Test Fix

The first account remains the Installation Owner even if its family membership role is temporarily changed from `owner` to `parent`. Installation-level authority and family-level role are separate concepts.

The previous tests incorrectly changed account 1 to the Parent role and expected database backup access to be denied. Because account 1 is still the configured Installation Owner, that expectation was invalid.

The corrected tests now:

- Identify the configured `installation_owner_account_id`.
- Select a different active account and family membership.
- Change that non-installation-owner membership to Parent.
- Confirm the Parent can export only their family data.
- Confirm the Parent receives HTTP 403 for the full database Backup & Restore Center.

The test reset process now uses SQLite's backup API instead of replacing test database files with `shutil.copy2`, reducing Windows locking and WAL-state problems when the full suite is run in one process.
