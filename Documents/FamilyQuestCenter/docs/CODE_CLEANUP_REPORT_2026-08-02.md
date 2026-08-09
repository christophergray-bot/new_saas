# Code Cleanup and Documentation Report

## Scope

This pass intentionally avoided feature changes and speculative removal of working code.

## Cleanup completed

- Removed the obsolete `templates/onboarding/family_setup.html.bak` file.
- Moved root-level release and security history into `docs/history/releases/` and `docs/history/security/`.
- Moved the legacy project-structure reference into developer documentation.
- Created a current developer documentation set and generated route/schema inventories.
- Preserved both page-header components because both are actively referenced.
- Preserved `static/phase_7_security.css` because it is loaded by `templates/base.html`.
- Preserved legacy migration tools as historical upgrade support.

## Deferred cleanup

Large-scale function consolidation, SQL abstraction, CSS pruning, and template-component merging were not performed because they require broader behavioral regression testing and provide limited benefit during release stabilization.
