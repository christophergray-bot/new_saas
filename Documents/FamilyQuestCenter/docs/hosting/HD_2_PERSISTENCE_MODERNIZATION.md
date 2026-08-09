# HD-2 Persistence Modernization

## What this package completes

- Flask-SQLAlchemy owns the shared SQLAlchemy engine.
- Flask-Migrate/Alembic owns hosted schema versions.
- Railway runs `flask --app app db upgrade` before the web process starts.
- PostgreSQL no longer creates tables during application import or worker boot.
- Local SQLite keeps the existing first-run initializer and test workflow.
- `/health` provides a lightweight Railway health check.

## Architecture during transition

The application contains more than 500 direct SQL calls. Converting all of
those safely is a multi-step migration. Existing routes continue through
`database.get_db()` and its PostgreSQL compatibility adapter while new and
converted modules can use `extensions.orm_db` and SQLAlchemy models.

This is intentional: schema lifecycle is now production-grade without forcing
an unsafe all-at-once rewrite of proven family workflows.

## Local validation

Install the new dependencies:

```bat
python -m pip install -r requirements.txt
```

Run:

```bat
python -W error::ResourceWarning -m unittest discover tests -v
```

Then start locally and perform a login/Quest smoke test.

## Railway staging

Required web-service variables:

- `DATABASE_URL=${{Postgres.DATABASE_URL}}`
- `FAMILY_QUEST_ENV=staging`
- `FAMILY_QUEST_DEBUG=0`
- `FAMILY_QUEST_REGISTRATION_MODE=closed`
- `FAMILY_QUEST_SECRET_KEY=<strong random value>`
- `FAMILY_QUEST_SESSION_SECONDS=3600`

Do not set `FAMILY_QUEST_DATABASE_PATH` on Railway.

Push the commit. Railway reads `railway.toml`, builds the service, runs the
baseline migration against the empty PostgreSQL service, then starts Gunicorn.

## First deployment acceptance criteria

1. Pre-deploy migration succeeds.
2. PostgreSQL shows the application tables plus `alembic_version`.
3. `/health` returns HTTP 200.
4. Registration remains closed until deliberately opened for staging setup.
5. No SQLite database file is created or used by Railway.
6. Deployment logs contain no SQLite-specific SQL failure.

## Next persistence work

Convert modules in this order while preserving regression tests:

1. Accounts, families, memberships, and family security
2. Children/users
3. Quests, schedules, and assignments
4. Adventures and journeys
5. Rewards and approvals
6. Reports, achievements, notifications, and administration

Each converted module should use SQLAlchemy Core/ORM statements and receive
new PostgreSQL-backed tests before the compatibility adapter is removed.
