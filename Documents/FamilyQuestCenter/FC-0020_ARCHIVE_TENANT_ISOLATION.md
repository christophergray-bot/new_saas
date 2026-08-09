# FC-0020 — Archive Center Tenant Isolation

## Status
Fixed in this build.

## Issue
Archive Center listing queries did not consistently filter records by the authenticated family. A new family could therefore see archived records belonging to another family.

## Corrections
- Added `family_id` filtering to archived children, quests, adventures, challenges, rewards, and reward categories.
- Changed archived achievement handling to use `family_achievements`, where family-specific archive state is stored.
- Scoped archived adventure schedules through both the related adventure and child ownership when older installations do not have a direct `family_id` column on `adventure_schedules`.
- Preserved tenant-safe restore behavior for direct family-owned tables.
- Added ownership checks for achievement and adventure-schedule restore operations.
- Added `tests/test_archive_tenant_isolation.py` covering cross-family listing and restore protection.

## Manual Regression Test
1. In Family A, archive a child, quest, adventure, challenge, reward, reward category, achievement, and schedule.
2. Sign in to Family B.
3. Confirm none of Family A's archived records appear in Family B's Archive Center or counts.
4. Archive different records in Family B and confirm only those records appear.
5. Attempt to submit a restore request for a Family A record while signed in as Family B.
6. Confirm the record remains archived.
7. Return to Family A and confirm its records can still be restored normally.
