
"""Regression coverage for installed-pack cosmetic manifest updates."""
from pathlib import Path
import json
import unittest

ROOT = Path(__file__).resolve().parents[1]

class ContentPackCosmeticUpdateTests(unittest.TestCase):
    def test_explorer_starter_has_twelve_image_avatars_with_valid_paths(self):
        manifest_path = ROOT / "content" / "packs" / "explorer_starter_pack" / "pack.json"
        pack = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(pack["version"], "2.1.1")
        self.assertEqual(len(pack["avatars"]), 12)
        for avatar in pack["avatars"]:
            self.assertIn("/explorer_starter_pack/characters/", avatar["image"])
            rel = avatar["image"].split("/explorer_starter_pack/", 1)[1]
            self.assertTrue((manifest_path.parent / rel).is_file(), avatar["image"])

    def test_parent_store_exposes_update_but_child_branch_precedes_it(self):
        text = (ROOT / "templates" / "parent" / "content_packs" / "store.html").read_text(encoding="utf-8")
        self.assertIn("content_packs.update", text)
        self.assertLess(text.index("{% elif store_child %}"), text.index("content_packs.update"))

if __name__ == "__main__":
    unittest.main()
