"""Automated regression/validation coverage.

File: tests/test_fqc_new_005_007_008_009_011_bundle.py
Reviewed for v1.7.0-rc1 cleanup.
"""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class BundledIssueRegressionTests(unittest.TestCase):
    def test_completed_book_read_again_posts_to_restart(self):
        text = (ROOT / "templates/quest_books/library.html").read_text(encoding="utf-8")
        self.assertIn("book.status == 'completed'", text)
        self.assertIn("child.restart_quest_book", text)
        self.assertIn('type="submit">Read Again</button>', text)

    def test_parent_timeout_is_seconds_with_600_default(self):
        settings = (ROOT / "models/settings.py").read_text(encoding="utf-8")
        template = (ROOT / "templates/parent_management/family_settings.html").read_text(encoding="utf-8")
        route = (ROOT / "routes/parent_management.py").read_text(encoding="utf-8")
        self.assertIn('"session_timeout_seconds": "600"', settings)
        self.assertIn('name="session_timeout_seconds"', template)
        self.assertIn('600 seconds (10 minutes)', template)
        self.assertIn('request.form.get("session_timeout_seconds", "600")', route)
        self.assertIn('86,400 seconds', route)

    def test_starter_pack_has_four_reward_categories_and_no_challenge(self):
        pack = json.loads((ROOT / "content/packs/explorer_starter_pack/pack.json").read_text(encoding="utf-8"))
        self.assertEqual(pack["challenges"], [])
        categories = pack["reward_categories"]
        self.assertEqual([c["name"] for c in categories], [
            "Treats & Snacks",
            "Screen & Game Time",
            "Activities & Adventures",
            "Special Privileges",
        ])
        self.assertEqual(len(categories), 4)

    def test_pack_service_supports_reward_categories_and_removed_challenge_cleanup(self):
        text = (ROOT / "services/content_packs.py").read_text(encoding="utf-8")
        self.assertIn('"reward_category": ("reward_categories", "active")', text)
        self.assertIn('for category in pack.get("reward_categories", [])', text)
        self.assertIn('item_type=\'challenge\'', text)
        self.assertIn('UPDATE family_challenges SET active=0', text)

    def test_family_dashboard_parent_locked_card_removed(self):
        text = (ROOT / "templates/family_dashboard.html").read_text(encoding="utf-8")
        self.assertNotIn("Parent Area Locked", text)
        self.assertNotIn("parent-access-card", text)


if __name__ == "__main__":
    unittest.main()
