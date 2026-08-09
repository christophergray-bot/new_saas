# Phase 2 Sprint 2C — Parent Accounts

Adds Application Owner support pages for individual parent accounts.

Included:
- Search and filtering by name, email, family, account status, role, and verification status.
- Parent account detail page with read-only family and security information.
- Password reset delivery, unlock, disable/reactivate, email verification, force logout, and audit history.
- Pending parent invitations appear in the account list and link to the related family.

Security boundaries:
- Passwords and password hashes are never displayed.
- The shared Family PIN is not managed from Parent Accounts.
- Parent profile, children, quests, adventures, and rewards remain outside this support interface.
