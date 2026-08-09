# Backup and Restore Guide

Backup and restore are installation-level maintenance functions and require the Owner role.

## Backup expectations

- Backups are SQLite database copies stored in the configured backup directory.
- Filenames include high-resolution timestamps to prevent collisions.
- Download and deletion must resolve files inside the configured backup directory only.

## Restore safety sequence

1. Validate the selected file and path.
2. Open it with SQLite and run an integrity check.
3. Close the validation connection.
4. Create a safety backup of the current database.
5. Restore through a temporary file and atomic replacement where supported.
6. Remove stale temporary files.
7. Reopen the application and run integrity checks.

Never test restoration against the only copy of a working family database.
