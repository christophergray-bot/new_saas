"""Automated regression/validation coverage.

File: tests/test_version_1_defaults.py
Reviewed for v1.7.0-rc1 cleanup.
"""
from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class VersionOneDefaultSettingsTests(unittest.TestCase):
    def test_source_defaults_match_version_one_configuration(self):
        from models.settings import DEFAULT_SETTINGS

        self.assertEqual(DEFAULT_SETTINGS["default_quest_difficulty"], "1")
        self.assertEqual(DEFAULT_SETTINGS["default_quest_stars"], "1")
        self.assertEqual(DEFAULT_SETTINGS["daily_reset_time"], "04:00")
        self.assertEqual(DEFAULT_SETTINGS["streak_grace_days"], "3")
        self.assertEqual(DEFAULT_SETTINGS["session_timeout_minutes"], "600")
        self.assertEqual(
            [DEFAULT_SETTINGS[f"xp_difficulty_{level}"] for level in range(1, 6)],
            ["1", "2", "4", "8", "16"],
        )


if __name__ == "__main__":
    unittest.main()
