# Local Security Work Items 11-15

## 11. Maximum field lengths — Completed
- Added `services/input_validation.py` with centralized server-side limits for common form fields.
- Added `maxlength` attributes to common HTML inputs and textareas.
- Added protections against excessive form fields and repeated list values.

## 12. Numeric, date, ID, and allowed-value validation — Partially completed and reviewed
- Existing feature routes already validate many numeric and allowed-value fields, including quest difficulty/stars, reward cost/quantity, mission schedules, settings ranges, and status filters.
- Central request-size and field-length validation now runs before route logic.
- Remaining feature-specific validation should continue as new fields are added; do not rely only on browser controls.

## 13. Active-family object validation — Verified for core records
- Child, user, quest, reward, assignment, adventure, report, and related model access is family-scoped through `get_current_family_id()` or tenant-aware service methods.
- `services/tenant_context.py` provides `family_owns`, `require_family_record`, and `family_scoped_route` helpers.
- A regression test was added for cross-family child-ID access.

## 14. Owner, Parent, Caregiver, and Child permissions — Test coverage added
- Global route protection requires an authenticated account and active family membership.
- Parent and administrative paths require owner or parent role.
- Caregiver access to parent paths is expected to return HTTP 403.
- Tests were added for unauthenticated, owner, caregiver, and unlocked-parent behavior.

## 15. Parent routes while PIN is locked — Test coverage added
- Parent routes redirect authenticated owners/parents to `/parent/login` until `parent_authenticated` is set.
- A test was added to confirm locked and unlocked behavior.

## Test execution note
The automated test module is included at `tests/test_security_11_15.py`. Syntax validation passed, but the tests could not be executed in the review container because Flask was not installed and external package installation was unavailable. Run locally with the project's Python environment:

```bash
python -m unittest tests/test_security_11_15.py -v
```

The tests copy `chorce.db` to a temporary directory and do not modify the working database.
