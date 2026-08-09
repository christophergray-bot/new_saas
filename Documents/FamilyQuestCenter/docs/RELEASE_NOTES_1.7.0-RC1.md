# Family Quest Center — Release Notes 1.7.0-rc1

**Release label:** 1.7.0-rc1  
**Review date:** August 9, 2026  
**Release state:** Release Candidate / pre-production testing

## Major capabilities represented in this candidate
- Family, parent, child, and Application Owner role workflows.
- Parent PIN protection with separate Parent and Child Mode inactivity windows.
- Quest, recurring mission, Adventure, reward, achievement, and reporting flows.
- Family-scoped Content Pack installation/update behavior.
- Explorer Starter Pack with Explorer character variants and reward categories.
- Character Workshop with Profile Character → Skin Tone → Frame → Theme flow.
- Interactive choose-your-path Quest Books with restart behavior and browser
  Read Aloud controls.
- Stripe billing/subscription integration and hosted email recovery workflows.
- Railway deployment configuration and system/release diagnostics.

## Cleanup performed for this reviewed package
- Removed Python bytecode and test caches.
- Removed backup (`.bak`) files and stale test-output artifacts.
- Removed the obsolete legacy `content/default_pack` manifest.
- Removed an accidental duplicate copy of the entire application that had been
  embedded under the Explorer character asset directory.
- Preserved Explorer PNG source images and WEBP runtime images.
- Removed Git metadata, `.env`, runtime backups, and the working database from
  this shareable reviewed package.
- Updated the Content Pack template to the current schema shape.
- Added lightweight file-purpose comments to Python/HTML files that did not
  already have a header/comment.
- Updated README and Known Limitations for the current application state.

## Before a final 1.7.0 release
- Run the complete automated test suite in the normal development environment.
- Complete the outstanding Dependabot dependency/security review.
- Complete hosted regression testing for billing, email recovery, sessions,
  Content Packs, Quest Books, backup/restore, and Application Owner tools.
- Confirm a production database/backup strategy.
