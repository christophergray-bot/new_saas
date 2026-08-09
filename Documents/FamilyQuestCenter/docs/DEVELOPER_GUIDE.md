# Family Quest Center Developer Guide

Updated: 2026-07-31

## Documentation standard

Python modules include a module-level purpose statement and docstrings for previously undocumented functions and classes. HTML/Jinja, CSS, JavaScript, SQL, and Windows batch files include format-appropriate developer headers. Comments explain ownership, purpose, and maintenance risks without changing application behavior.

## Source organization

- `app.py` creates the Flask application and registers feature routes.
- `routes/` contains request handlers and page workflows.
- `models/` contains data-access and domain operations.
- `services/` contains reusable business logic and tenant/family safeguards.
- `templates/` contains Jinja user-interface templates.
- `static/` contains styling, scripts, and image assets.
- `migrations/` and `schema.sql` define database evolution and clean-install structure.
- `content/` contains structured game content and starter packs.
- `docs/` contains release history, test checklists, and developer references.

## Maintenance rules

1. Preserve tenant and family isolation in every database query and route.
2. Validate parent authorization before administrative changes.
3. Keep schema, migrations, models, and clean-install packaging synchronized.
4. Do not edit generated `.pyc` files or the contents of `__pycache__/`.
5. Treat `old.chorce.db` as historical data; do not ship it as a clean production database.
6. Run Python compilation and the full regression checklist after code changes.
7. Update the file inventory when files are added, removed, or renamed.

## Safe release check

Before packaging a release, compile all Python files, initialize a fresh database from the clean schema, exercise authentication and tenant isolation, test parent and child workflows, and verify that the release archive excludes development data and generated caches.
