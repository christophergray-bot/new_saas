# Architecture Overview

## Application shape

Family Quest Center is a Flask application using Jinja templates and SQLite for the local edition. `app.py` is the application factory and composition root.

Request flow:

1. Flask receives the request.
2. Global input and CSRF checks run.
3. Account, family membership, role, and Parent PIN controls are applied.
4. A blueprint route handles the workflow.
5. Models perform parameterized data access.
6. Services provide reusable security and business rules.
7. Jinja renders escaped output.
8. Security headers are attached to the response.
9. The request-scoped SQLite connection is closed during teardown.

## Main layers

- `routes/`: HTTP workflows, redirects, form handling, and response selection.
- `models/`: database operations and domain queries.
- `services/`: reusable business logic, authentication, validation, tenant safeguards, and migrations that must run at startup.
- `templates/`: Jinja presentation layer.
- `static/`: CSS and JavaScript.
- `content/`: game content definitions, not application source code.
- `tests/`: security regression tests using temporary database copies.

## Security boundaries

The authenticated account does not directly establish data ownership. The active membership resolves the current `family_id`; all tenant-owned data operations must use that value. Administrative interfaces additionally require an Owner or Parent role and an unlocked Parent PIN session. Installation-level maintenance actions are Owner-only.

## Startup behavior

A missing database is initialized from `schema.sql`. Startup services ensure required multi-family, mission isolation, achievement, and onboarding structures are available. These services must be idempotent and must close direct SQLite connections.
