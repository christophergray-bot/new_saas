# Backup and Restore Test Fix

Two Windows test failures were corrected:

1. The backup integrity-check SQLite connection was not explicitly closed, which left the corrupt test file locked on Windows.
2. Backup filenames used only one-second precision. A restore-created safety backup could reuse and overwrite the source backup when both were created in the same second. Backup names now include microseconds.

The restore workflow now closes every validation connection, uses collision-resistant backup names, removes any stale restore temporary file, and then atomically replaces the test database.
