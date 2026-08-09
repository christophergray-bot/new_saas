# Sprint 5 - Parent Two Invitation and Authentication

Implemented 2026-08-05.

## Final behavior

- Parent Two accepts a one-time invitation tied to the invited email address.
- A new Parent Two creates an independent account password and display name.
- An existing account confirms its own current password before joining the family.
- After acceptance, Parent Two is signed into their account and sent to the shared Family PIN unlock screen.
- Parent Two is never sent to the owner-only Family PIN setup screen.
- The Family PIN remains shared by Parent One and Parent Two.
- Parent One can resend or cancel a pending invitation.
- Resending invalidates the prior invitation link and creates a new seven-day, one-time link.
- Accepted, cancelled, replaced, and expired invitation links cannot be reused.

## Validation

- Python compilation passed.
- Jinja parsing passed for the modified templates.
- Sprint-specific static validation passed.
- Full Flask tests require the project dependencies in requirements.txt; Werkzeug was unavailable in the packaging workspace.
