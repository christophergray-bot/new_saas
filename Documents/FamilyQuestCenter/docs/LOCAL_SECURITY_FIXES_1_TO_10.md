# Local Security Fixes 1–10

Applied to the uploaded working package on 2026-08-02.

## Completed

1. Removed obsolete `old.chorce.db` files.
2. Removed duplicate databases from `content/` while preserving the root working `chorce.db`.
3. Removed Python caches and compiled files.
4. Added a comprehensive `.gitignore`.
5. Archived historical release notes and testing checklists under `docs/`.
6. Confirmed `content/` is required for structured game content.
7. Removed the duplicate application tree from `content/`, preserving only `cosmetics.json` and the canonical `packs/` directory.
8. Added explicit CSRF hidden fields to POST forms that did not already contain one.
9. Enabled SQLite foreign-key enforcement on every normal application connection.
10. Ran SQLite integrity and foreign-key checks against the preserved working database.

## Database check results

```text
Integrity check: ['ok']
Foreign-key violations: 0
Foreign-key enable test: 1
```

## Important

The root `chorce.db` remains in this reviewed working package so existing data is preserved. It is excluded by `.gitignore` and must be removed or replaced with a fresh database in the final clean-install release.
