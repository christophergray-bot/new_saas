# FC-0018 — Starter Pack Onboarding Fix

## Problem

A parent could select the Default Family Pack during account registration, but
onboarding completed without installing the pack.

## Cause

The cleanup removed the legacy duplicate starter manifest under
`content/packs`. The Pack Manager normally registers manifests in the
`content_packs` catalog when its discovery page is opened. Registration calls
`install_pack()` before that page is visited. The installer then attempted to
create a `family_content_packs` row whose foreign-key catalog record did not yet
exist.

Account creation deliberately catches optional pack-install errors, so the
family account survived while the starter content was skipped.

## Correction

`install_pack()` now registers or refreshes its own manifest in the pack catalog
before creating any family installation records. Installation is self-contained
and no longer depends on opening Pack Manager first.

## Regression tests

`tests/test_onboarding_content_pack.py` verifies:

1. Selecting the Default Family Pack installs the pack and creates starter
   quests, adventures, and rewards.
2. Selecting Empty Family creates no starter pack or starter content.
