"""Regression coverage for parent-only Pack Store archive controls."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]

class PackStoreArchiveControlTests(unittest.TestCase):
    def test_parent_store_has_archive_action(self):
        text = (ROOT / "templates/parent/content_packs/store.html").read_text(encoding="utf-8")
        self.assertIn("url_for('content_packs.archive'", text)
        self.assertIn("📦 Archive Pack", text)

    def test_parent_detail_has_archive_action(self):
        text = (ROOT / "templates/parent/content_packs/detail.html").read_text(encoding="utf-8")
        self.assertIn("url_for('content_packs.archive'", text)
        self.assertIn("📦 Archive Pack", text)

    def test_child_and_request_branches_do_not_post_to_archive(self):
        store = (ROOT / "templates/parent/content_packs/store.html").read_text(encoding="utf-8")
        detail = (ROOT / "templates/parent/content_packs/detail.html").read_text(encoding="utf-8")

        # Archive action occurs only after the request_mode/store_child branches,
        # in the parent-management branch of each shared template.
        self.assertLess(store.index("{% elif store_child %}"), store.index("url_for('content_packs.archive'"))
        self.assertLess(detail.index("{% elif store_child %}"), detail.index("url_for('content_packs.archive'"))

if __name__ == "__main__":
    unittest.main()
