# Parent PIN Gate Recovery

The Parent PIN gate now includes a **Reset PIN with Account Password** option.

The recovery workflow is available before the Parent Area is unlocked and requires:

- An authenticated account session
- An Owner or Parent family role
- The correct account password
- A new four-digit PIN entered twice
- CSRF validation and rate limiting

A successful reset replaces the family PIN, unlocks the Parent Area for the current session, rotates the CSRF token, and records an audit event.

Caregivers and unauthenticated users cannot reset the Parent PIN.
