# System Health Update

The former Integrity Check page is now a grouped System Health dashboard.

It includes:
- Overall health status and pass/warning/error totals
- Run timestamp and application version
- Database and tenant-reference checks
- Family-scoped Parent PIN status
- Registration mode and installation-owner status
- Default and installed Content Pack status
- Backup status
- Quick links to resolve warnings

The Parent PIN check now reads from the current family's `family_security` record rather than the obsolete legacy `settings.parent_pin_hash` value.
