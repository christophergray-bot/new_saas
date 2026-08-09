FAMILY QUEST CENTER — CLEAN ACCEPTANCE TEST DATABASE
====================================================

Purpose
-------
This package contains a clean SQLite database for testing the complete
new-customer experience. It contains the current schema and required global
system defaults, but no customer or family data.

Confirmed empty customer data
-----------------------------
- Account users: 0
- Families: 0
- Family memberships: 0
- Parent security records: 0
- Children/users: 0
- Quests: 0
- Assignments/missions: 0
- Journeys: 0
- Adventures: 0
- Active adventure instances: 0
- Challenges: 0
- Rewards: 0
- Reward requests: 0
- Progress/history/activity records: 0

Preserved system data
---------------------
- Database schema and indexes
- Application/version metadata
- Migration history
- Built-in achievement definitions
- Built-in reward categories
- Default application settings

How to test
-----------
1. Extract the ZIP into a new folder.
2. Run Start Family Quest Center.bat.
3. Confirm the public landing page opens.
4. Select Start Your Adventure.
5. Register the first parent and family.
6. Verify the new family begins with no children, quests, missions,
   adventures, challenges, rewards, approvals, or activity from another family.
7. Add content from scratch and test the normal workflow.

Automatic first-run database creation
-------------------------------------
If chorce.db is deleted or absent, the application now creates a fresh empty
schema automatically from schema.sql when it starts. Required system defaults
may be restored, but no account, family, child, quest, mission, adventure,
challenge, or reward data is seeded.

Important
---------
Use this package only for acceptance testing. Keep your populated development
copy in a separate folder.
