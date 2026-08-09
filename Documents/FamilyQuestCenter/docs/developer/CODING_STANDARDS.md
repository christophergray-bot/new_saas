# Coding Standards

## Python

- Use the application factory and Flask blueprints.
- Keep route handlers focused on HTTP workflow; move reusable rules into services and data operations into models.
- Use descriptive names and short docstrings for non-obvious behavior.
- Use `pathlib.Path` for filesystem paths.
- Use context managers or `try/finally` for direct SQLite connections.
- Do not catch broad exceptions unless the error is logged safely and the application can recover.

## Database and tenant safety

- Use parameterized SQL for every value.
- Resolve `family_id` from authenticated membership, never from hidden fields or query parameters.
- Include `family_id` in reads and writes for tenant-owned records.
- Return 404 rather than revealing another family's object exists.
- Keep foreign keys enabled and verify migrations with `foreign_key_check`.

## Forms and templates

- Every POST form requires an explicit CSRF token.
- Enforce limits server-side; HTML `maxlength` is only a usability aid.
- Keep Jinja autoescape enabled and avoid `|safe` for user content.
- Reuse existing partials before creating new UI components.

## Changes

- Do not mix feature additions into security or cleanup changes.
- Add or update tests for authorization, tenant isolation, and destructive operations.
- Update current documentation and release notes with meaningful behavior changes.
