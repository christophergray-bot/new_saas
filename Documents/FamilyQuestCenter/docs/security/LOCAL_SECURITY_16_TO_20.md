# Local Security Hardening — Items 16–20

Date: 2026-08-02

## Completed work

### 16. Cross-family URL and object-ID testing

Added automated checks for cross-family child, quest, reward, and reward-request IDs. The review also identified and corrected an unscoped reward activation update.

### 17. Sensitive logging review

Added `sanitize_log_text()` to redact common password, PIN, CSRF, token, session, authorization, cookie, and secret values before they are stored in the audit or error tables. Log text is also length-bounded.

### 18. Backup and restore security

Added automated tests for:

- backup creation and SQLite integrity;
- backup deletion;
- path-traversal rejection;
- corrupted-backup rejection;
- valid restore with automatic safety copy;
- preservation of the working database when restore validation fails.

Backup storage is now configurable through `FAMILY_QUEST_BACKUP_DIRECTORY`, allowing security tests to use an isolated temporary folder.

Maintenance backup, restore, download, deletion, export, and integrity routes now require the `owner` role. A normal parent cannot access installation-level database operations.

### 19. Foreign-key delete behavior

The current schema primarily uses restrictive foreign keys rather than automatic `ON DELETE CASCADE`. This is a safe default for Family Quest Center because an accidental child, quest, or assignment deletion is blocked rather than silently removing history.

Confirmed on a copied database:

- `PRAGMA integrity_check`: `ok`
- `PRAGMA foreign_key_check`: zero violations
- deletion of a child with dependent records: blocked with `sqlite3.IntegrityError`

The application should continue using archive/deactivate workflows for normal records instead of hard deletion.

### 20. Automated tenant-isolation regression suite

Added `tests/test_security_16_20.py`. It uses a temporary database copy and tests tenant isolation, logging redaction, backup/restore safety, foreign-key protection, family-scoped exports, and maintenance-role restrictions.

The family export was corrected. It previously exported all rows from shared tenant tables. It now exports only the active family's records. Shared achievement definitions remain included as non-tenant reference data.

## Running the tests

From the project folder:

```text
python -m unittest tests/test_security_11_15.py tests/test_security_16_20.py -v
```

Or on Windows, double-click:

```text
Run Local Security Tests.bat
```

The tests copy `chorce.db` before making changes. They do not restore over or modify the working database.
