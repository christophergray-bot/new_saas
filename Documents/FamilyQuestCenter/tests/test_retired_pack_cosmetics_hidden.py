"""Automated regression/validation coverage.

File: tests/test_retired_pack_cosmetics_hidden.py
Reviewed for v1.7.0-rc1 cleanup.
"""

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class RetiredPackCosmeticsTests(unittest.TestCase):
    def test_explorer_starter_manifest_no_longer_contains_legacy_icon_keys(self):
        path = ROOT / "content" / "packs" / "explorer_starter_pack" / "pack.json"
        pack = json.loads(path.read_text(encoding="utf-8"))
        keys = {item["key"] for item in pack.get("avatars", [])}
        self.assertNotIn("explorer_boy", keys)
        self.assertNotIn("explorer_girl", keys)
        self.assertEqual(len([k for k in keys if k.startswith("explorer_boy_")]), 6)
        self.assertEqual(len([k for k in keys if k.startswith("explorer_girl_")]), 6)

    def test_family_cosmetic_filter_requires_key_to_exist_in_current_manifest(self):
        text = (ROOT / "models" / "cosmetics.py").read_text(encoding="utf-8")
        self.assertIn("manifest_cosmetic_keys", text)
        self.assertIn('(row["category"], row["item_key"]) not in current_keys', text)

    def test_core_defaults_remain_two(self):
        path = ROOT / "content" / "cosmetics.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        keys = [item["key"] for item in data.get("avatars", [])]
        self.assertEqual(keys, ["adventurer", "adventurer_girl"])

if __name__ == "__main__":
    unittest.main()
