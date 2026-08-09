# Known Limitations — Version 1.7.0-rc1

Family Quest Center is still in release-candidate testing and should not yet be
treated as a finished production SaaS release.

- The hosted environment currently uses SQLite. Production-scale concurrency,
  backup, restore, and disaster-recovery behavior require continued validation.
- Paid Content Pack/store support is not yet considered production-complete.
- Quest Book Read Aloud relies on the browser Web Speech API, so voice quality,
  available voices, and support vary by browser/device.
- Application Owner, billing, account recovery, and email workflows should
  continue to receive hosted end-to-end testing before public launch.
- Dependabot currently reports four dependency findings (three moderate and one
  low) that remain scheduled for a dedicated dependency/security review.
- Content Pack compatibility should be regression-tested whenever pack schema or
  installation/update behavior changes.
- Production registration should remain deliberately controlled until launch
  readiness, billing enforcement, support procedures, backups, and recovery
  procedures have been signed off.

This file should be updated whenever a limitation is resolved or a new release
candidate is labeled.
