# Release Checklist

## Code and tests

- [ ] No unplanned features were added during stabilization.
- [ ] `python -W error::ResourceWarning -m unittest discover tests -v` passes.
- [ ] All Python files compile.
- [ ] Database integrity and foreign-key checks pass.
- [ ] Tenant-isolation and role tests pass.

## Package contents

- [ ] No `.env`, secrets, logs, backups, caches, `.pyc`, or obsolete databases.
- [ ] Clean-install package contains no family or account data.
- [ ] Required content packs and static assets are present.
- [ ] `requirements.txt`, startup instructions, schema, and migrations are present.
- [ ] Version values and release notes agree.

## Clean-install acceptance

- [ ] Application starts in a clean folder.
- [ ] Database initializes automatically.
- [ ] First account and family setup completes.
- [ ] Parent PIN setup and unlock work.
- [ ] Child, quest, assignment, reward, and adventure workflows work.
- [ ] Backup creation and restore are tested against disposable data.
