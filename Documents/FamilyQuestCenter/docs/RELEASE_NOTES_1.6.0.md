# Family Quest Center 1.6.0 — Milestone 1 Readiness

## Recovery

- Added Parent PIN reset using the signed-in account password.
- Restricted Parent PIN changes and resets to Owner and Parent roles.
- Clarified that local account-password recovery requires administrator or backup
  recovery until hosted email services exist.

## Content Packs

- Removed the obsolete duplicate Explorer Starter manifest.
- Removed Coming Soon preview cards from the local Pack Manager.
- Added `tools/validate_content_packs.py`.
- Confirmed seven unique bundled pack manifests pass structural validation.
- Preserved built-in core-pack archive protection.

## Registration readiness

- Added explicit registration modes: local, closed, open, and trial.
- Production now defaults to closed registration.
- Added a clear Registration Closed page.
- Updated public homepage calls to action to respect registration status.

## Documentation and packaging

- Replaced the obsolete root README.
- Added a local user guide and known-limitations document.
- Added clean-install packaging guidance.
