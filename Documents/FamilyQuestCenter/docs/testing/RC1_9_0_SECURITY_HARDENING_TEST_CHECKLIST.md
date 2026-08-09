# RC1.9.0 Security Hardening Test Checklist

## CSRF
- [ ] Normal login, registration, PIN, create, edit, archive, approval, assignment, pack, and maintenance forms still work.
- [ ] Remove `csrf_token` in browser developer tools and submit a POST; verify HTTP 400.
- [ ] Change the token value and verify HTTP 400.
- [ ] Refresh the page and verify a valid action works again.

## Rate limiting
- [ ] Enter five incorrect account passwords and verify temporary throttling.
- [ ] Enter five incorrect parent PINs and verify temporary throttling.
- [ ] Verify a successful login clears prior failures.
- [ ] Verify throttling one account does not block a different account from the same normal workflow unless the IP limit is intentionally reached.

## Sessions and secrets
- [ ] Development mode starts without an environment secret for local use.
- [ ] Production mode refuses to start with a missing or short secret.
- [ ] Production cookies include Secure, HttpOnly, and SameSite=Lax.
- [ ] Account login replaces the prior session.
- [ ] Password change signs the current browser out and requires the new password.
- [ ] Session expires after the configured lifetime.

## Headers and hosting
- [ ] Responses include CSP, nosniff, Referrer-Policy, Permissions-Policy, and frame-ancestors 'none'.
- [ ] Production HTTPS responses include HSTS.
- [ ] Gunicorn starts using the included Procfile.

## Tenant isolation (two-family test)
- [ ] Reports show only the signed-in family.
- [ ] Parent notifications show only the signed-in family.
- [ ] Dashboard counts and active Adventures show only the signed-in family.
- [ ] Quest, Adventure, Reward, Challenge, Archive, Approval, and Pack pages show only the signed-in family.
- [ ] Change child, quest, assignment, Adventure instance, reward-request, and notification IDs in URLs/forms; verify denial or not found.
- [ ] Family A cannot pause, unassign, cancel, approve, dismiss, archive, restore, download, or edit Family B records.

## Regression
- [ ] Parent and child end-to-end workflows pass.
- [ ] Content pack install/archive/restore passes.
- [ ] Backup and restore passes with CSRF enabled.
