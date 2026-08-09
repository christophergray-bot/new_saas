# Family Quest Center Security Configuration

## Production environment

Set `FAMILY_QUEST_ENV=production`. In production the application refuses to start unless `FAMILY_QUEST_SECRET_KEY` is at least 32 characters. Generate a unique random secret and store it only in the hosting provider's secret-variable system.

Production mode enables HTTPS-only session cookies and HSTS. Deploy behind Railway HTTPS using the included Gunicorn `Procfile`; do not run `python app.py` as the public server.

## Controls included in RC1.9.0 Phase 1

- CSRF validation for every POST, PUT, PATCH, and DELETE request.
- Automatic CSRF fields for HTML forms.
- Persistent throttling for account login, parent PIN setup/login, registration, and password-change verification.
- Secure, HttpOnly, SameSite session cookies in production.
- One-hour default session lifetime, configurable with `FAMILY_QUEST_SESSION_SECONDS`.
- Session reset after account login/registration and forced sign-in after a password change.
- CSP, frame blocking, MIME sniffing protection, referrer policy, permissions policy, and HSTS in production.
- Proxy handling for Railway forwarded HTTPS and client-address headers.

## Required deployment checks

1. Confirm `FAMILY_QUEST_ENV=production`.
2. Confirm `FAMILY_QUEST_SECRET_KEY` is unique and not stored in source control.
3. Confirm Railway serves the site over HTTPS.
4. Confirm the process starts with Gunicorn.
5. Confirm the database path points to durable storage or migrate the hosted service to PostgreSQL before broad public use.
6. Test a missing CSRF token, repeated failed login, repeated failed PIN, session timeout, and logout.
7. Complete the tenant-isolation checklist with two separate families.
