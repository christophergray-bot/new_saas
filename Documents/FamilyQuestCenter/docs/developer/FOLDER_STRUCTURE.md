# Folder Structure

| Path | Purpose |
|---|---|
| `app.py` | Application factory, blueprint registration, global handlers |
| `config.py` | Environment-aware configuration |
| `database.py` | Request-scoped SQLite connection management |
| `schema.sql` | Clean-install database schema |
| `routes/` | Feature blueprints and web workflows |
| `models/` | Domain queries and database changes |
| `services/` | Shared logic and security controls |
| `templates/` | Jinja templates |
| `static/` | Browser assets |
| `content/` | Content packs and cosmetic definitions |
| `migrations/` | Retained database migrations |
| `tools/legacy_migrations/` | Historical one-time migration utilities |
| `tests/` | Automated regression tests |
| `docs/developer/` | Current technical documentation |
| `docs/security/` | Security implementation records |
| `docs/testing/` | Manual and release-specific test checklists |
| `docs/history/` | Archived sprint and release records |

Generated files, databases, logs, backups, `.env`, caches, and compiled Python files must remain excluded from Git and public release packages.
