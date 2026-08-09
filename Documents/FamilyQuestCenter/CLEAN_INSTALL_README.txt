FAMILY QUEST CENTER v1.1.0 — CLEAN LOCAL INSTALLATION
=====================================================

This package is intended for a new local installation. It contains a fresh
SQLite database with no accounts, children, quests, assignments, rewards,
adventures, activity, audit history, or personal family information.

Built-in system definitions, required settings, and schema structures are
included so the application can start normally.

INSTALLATION
------------
1. Extract the ZIP into a new folder. Do not overwrite your working copy.
2. Install Python 3.13 or another supported Python 3 version.
3. Open Command Prompt in the extracted folder.
4. Install dependencies:

      python -m pip install -r requirements.txt

5. Start Family Quest Center:

      Start Family Quest Center.bat

   Or:

      python app.py

6. Open http://127.0.0.1:5000 if the browser does not open automatically.
7. Register the first account and complete family setup.

IMPORTANT
---------
- Keep this installation on a trusted local computer or trusted home network.
- Do not expose the Flask development server directly to the Internet.
- Keep chorce.db private; it will contain family and child information after use.
- Back up chorce.db before replacing or upgrading the application.

DATABASE RESET
--------------
To create another fresh database:
1. Close Family Quest Center.
2. Back up or rename chorce.db.
3. Run: python init_db.py
4. Start the application normally.

Never run the reset steps against a database whose data you need to keep.
