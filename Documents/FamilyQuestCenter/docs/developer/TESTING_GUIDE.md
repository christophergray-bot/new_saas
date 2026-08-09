# Testing Guide

## Full automated suite

Run from the project root:

```bat
python -m unittest discover tests -v
```

Strict resource-warning run:

```bat
python -W error::ResourceWarning -m unittest discover tests -v
```

The tests use isolated temporary databases and backup folders. They must never modify the working `chorce.db`.

## Current security coverage

The suite covers authentication gates, Parent PIN locking, role restrictions, cross-family access, input limits, CSRF-related workflows, family-scoped exports, backup and restore protections, log redaction, foreign keys, and orphan prevention.

## Release validation

1. Run all automated tests.
2. Compile all Python files.
3. Initialize a database in a clean temporary folder.
4. Run SQLite integrity and foreign-key checks.
5. Manually test onboarding, Parent Dashboard, child mode, assignments, rewards, adventures, reports, backup, and restore.
6. Confirm release archives contain no personal data, logs, backups, caches, or secrets.
