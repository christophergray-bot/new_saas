# HD-1.5 Database Abstraction

Family Quest Center now selects its database backend automatically:

- No `DATABASE_URL`: local SQLite through `FAMILY_QUEST_DATABASE_PATH`.
- `DATABASE_URL` present: PostgreSQL through SQLAlchemy and psycopg.

## Railway staging variables

Set these on the web service:

- `DATABASE_URL=${{Postgres.DATABASE_URL}}`
- `FAMILY_QUEST_ENV=staging`
- `FAMILY_QUEST_SECRET_KEY=<random 32+ character value>`
- `FAMILY_QUEST_DEBUG=0`
- `FAMILY_QUEST_REGISTRATION_MODE=closed`
- `FAMILY_QUEST_SESSION_SECONDS=3600`

Do not set `FAMILY_QUEST_DATABASE_PATH` on Railway.

## Important migration status

This is the first PostgreSQL compatibility pass. The connection layer translates
legacy `?` parameters, SQLite table-introspection calls, and `INSERT OR IGNORE`.
The hosted schema is generated in `schema_postgres.sql` from the current clean
SQLite schema. Run the full staging smoke test before inviting beta users.

Local SQLite remains the regression baseline. Run:

    python -W error::ResourceWarning -m unittest discover tests -v

## Deployment

Railway uses the existing Procfile and Gunicorn. The first PostgreSQL boot creates
an empty schema; it does not copy local families or development data.
