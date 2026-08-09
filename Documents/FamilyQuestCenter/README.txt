FAMILY QUEST CENTER
Version 1.7.0-rc1 — Release Candidate 1
Reviewed: August 9, 2026

OVERVIEW
Family Quest Center is a Flask application that helps families manage quests,
recurring missions, adventures, rewards, achievements, Explorer profiles,
content packs, and interactive Quest Books in a family-scoped workspace.

CURRENT RELEASE STATUS
- Active pre-production / release-candidate testing.
- Local and Railway-hosted testing are supported.
- Parent password and PIN protections are implemented.
- Email-based password/PIN recovery workflows are available when email is configured.
- Stripe subscription/billing support is implemented and remains subject to production validation.
- Content Packs are family-scoped and support quests, adventures, books, cosmetics,
  reward categories, and other pack content.
- Quest Books support choose-your-path reading and browser-based Read Aloud.
- Application Owner / management tooling is present for system operations.

STARTING THE APPLICATION
1. Install a supported Python version.
2. From this folder, install dependencies:
       python -m pip install -r requirements.txt
3. Configure environment variables using .env.example as the reference.
4. Start with:
       Start Family Quest Center.bat
   or:
       python app.py
5. Open the local address displayed in the terminal.

TESTING
Run the test suite from the project root:
    python -m pytest -q

Validate bundled Content Packs:
    python tools/validate_content_packs.py

SESSION DEFAULTS
- Parent Area inactivity timeout: 600 seconds (10 minutes).
- Child Mode inactivity timeout: 43,200 seconds (12 hours).
- Returning from Child Mode to Parent Area requires the Parent PIN.

CONTENT PACKS
The canonical starter content is:
    content/packs/explorer_starter_pack/

The obsolete content/default_pack tree has been removed from this reviewed build.

WORKING DATA WARNING
Do not commit or publish .env files, working databases, backups, logs, test caches,
or user-uploaded content. This reviewed package intentionally excludes local
secrets, Git metadata, runtime backups, and the working database.

IMPORTANT FILES
- docs/USER_GUIDE.md
- docs/KNOWN_LIMITATIONS.md
- docs/RELEASE_NOTES_1.7.0-RC1.md
- docs/CODE_CLEANUP_REVIEW_2026-08-09.md
- docs/developer/BACKUP_RESTORE_GUIDE.md
- docs/developer/TESTING_GUIDE.md
- docs/developer/RELEASE_CHECKLIST.md
