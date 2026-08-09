# Database Schema Guide

The clean-install schema is defined by `schema.sql`. Incremental changes are retained in `migrations/`; legacy one-time tools are under `tools/legacy_migrations/`.

## Current schema inventory

- Tables defined: **23**
- Indexes defined: **13**

## Tables

- `achievements`
- `application_info`
- `assignments`
- `audit_log`
- `chores`
- `error_log`
- `family_challenges`
- `migration_history`
- `notification_dismissals`
- `point_history`
- `quest_chain_instances`
- `quest_chain_steps`
- `quest_chains`
- `quest_schedules`
- `reward_categories`
- `reward_history`
- `reward_requests`
- `rewards`
- `settings`
- `star_transactions`
- `user_achievements`
- `users`
- `xp_history`

## Database rules

- Every request connection enables `PRAGMA foreign_keys = ON`.
- Family-owned records must be filtered by the authenticated membership's `family_id`.
- Use parameterized SQL; never concatenate browser input into SQL.
- Prefer archive/deactivate workflows where history must be retained.
- Update `schema.sql`, applicable migrations, models, tests, and clean-install validation together.

## Validation commands

```bat
python -m unittest discover tests -v
```

```sql
PRAGMA integrity_check;
PRAGMA foreign_key_check;
```
