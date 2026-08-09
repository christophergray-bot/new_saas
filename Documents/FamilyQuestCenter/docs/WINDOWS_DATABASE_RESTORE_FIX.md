# Windows Database Restore Fix

## Problem

Older restore logic copied a selected backup to `chorce.restore.tmp` and then
used a file rename to replace `chorce.db`. Windows returns `WinError 5` when
Flask or SQLite still has the destination database open.

## Correction

- The maintenance route closes the current request-scoped database connection
  before restore begins.
- Restore now uses SQLite's supported backup API to copy the selected backup
  into the application database instead of replacing the file.
- A safety backup is created before every restore.
- The restored database is checked with `PRAGMA integrity_check`.
- If restoration or validation fails, the safety backup is copied back.
- Obsolete `.restore.tmp` debris is removed automatically.

## Expected workflow

1. Create or select a backup.
2. Type `RESTORE` and confirm.
3. Family Quest Center creates a safety backup.
4. The selected backup is restored.
5. Restart Family Quest Center when prompted.
