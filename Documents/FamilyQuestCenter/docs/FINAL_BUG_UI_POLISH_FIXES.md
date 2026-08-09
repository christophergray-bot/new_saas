# Final Bug and UI Polish Fixes

## FC-0019 — Active libraries
The Adventure Library now calls the active-only Adventure query. The Quest Library already filtered inactive records. A regression test verifies that archived Quests and Adventures are absent from active libraries.

## FC-0020 — Family Settings alignment
Both Family Identity fields now use matching label/input/helper-text structure, keeping the two controls aligned and visually balanced.

## FC-0021 — Approval filters
Mission/Adventure Approval now uses the same shared `filter-tabs` pill control as Reward Requests.

## TEST-0003 — Onboarding fixture
The onboarding test now initializes Content Pack tracking tables explicitly, including when the Empty Family path correctly skips pack installation.
