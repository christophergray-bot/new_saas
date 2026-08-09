Family Quest Center Test Baseline

This sanitized SQLite database is used only by automated regression tests.
It replaces the former dependency on the developer's working chorce.db.

Rules:
- Do not store real family names, emails, passwords, PINs, or production data here.
- Keep schema/content-pack metadata aligned with the current release candidate.
- Tests copy this file into temporary directories before modifying it.
